#!/usr/bin/env python3
import json
import os
import ssl
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request


NS = os.getenv("WATCHDOG_NAMESPACE", "vault")
LEASE_NS = os.getenv("LEASE_NAMESPACE", os.getenv("POD_NAMESPACE", "helm-watchdogs"))
POD_NAME = os.getenv("POD_NAME", "unknown")
LEASE_NAME = os.getenv("LEASE_NAME", "helm-watchdogs-leader")
VAULT_SERVICE = os.getenv("VAULT_SERVICE", "vault-active")
INTERVAL = int(os.getenv("WATCHDOG_INTERVAL_SECONDS", "10"))
AUTO_UNSEAL = os.getenv("AUTO_UNSEAL", "true").lower() == "true"
ALLOW_POD_DELETE = os.getenv("ALLOW_POD_DELETE", "false").lower() == "true"
MAX_REMEDIATIONS = int(os.getenv("MAX_REMEDIATIONS_PER_HOUR", "3"))


def log(event, **fields):
    print(json.dumps({"component": "helm-watchdogs", "event": event, **fields}, sort_keys=True), flush=True)


def request(url, method="GET", body=None, headers=None, context=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5, context=context) as response:
        raw = response.read()
        return response.status, json.loads(raw) if raw else {}


def kube(path, method="GET", body=None):
    token = open("/var/run/secrets/kubernetes.io/serviceaccount/token").read().strip()
    ca = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    context = ssl.create_default_context(cafile=ca)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    _, result = request(f"https://kubernetes.default.svc{path}", method, body, headers, context)
    return result


def leader_check():
    path = f"/apis/coordination.k8s.io/v1/namespaces/{LEASE_NS}/leases/{LEASE_NAME}"
    now = time.time()
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    desired = {
        "apiVersion": "coordination.k8s.io/v1",
        "kind": "Lease",
        "metadata": {"name": LEASE_NAME, "namespace": LEASE_NS},
        "spec": {"holderIdentity": POD_NAME, "leaseDurationSeconds": 30,
                 "renewTime": now_iso, "acquireTime": now_iso,
                 "leaderTransitions": 0},
    }
    try:
        lease = kube(path)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            log("lease_read_failed", pod=POD_NAME, status=exc.code)
            return False
        try:
            kube(f"/apis/coordination.k8s.io/v1/namespaces/{LEASE_NS}/leases", "POST", desired)
            log("leadership_acquired", pod=POD_NAME)
            return True
        except Exception as create_exc:
            log("lease_create_failed", pod=POD_NAME, error=str(create_exc))
            return False
    except Exception as exc:
        log("lease_read_failed", pod=POD_NAME, error=str(exc))
        return False
    spec = lease.get("spec", {})
    holder = spec.get("holderIdentity")
    renew = spec.get("renewTime")
    try:
        renew_time = datetime.fromisoformat(renew.replace("Z", "+00:00")).timestamp() if renew else 0
        expired = not renew or now - renew_time > int(spec.get("leaseDurationSeconds", 30))
    except (TypeError, ValueError):
        expired = True
    if holder not in (None, POD_NAME) and not expired:
        return False
    desired["metadata"]["resourceVersion"] = lease["metadata"].get("resourceVersion")
    desired["spec"]["leaderTransitions"] = int(spec.get("leaderTransitions", 0)) + (0 if holder == POD_NAME else 1)
    if holder == POD_NAME:
        desired["spec"]["acquireTime"] = spec.get("acquireTime", str(now))
    try:
        kube(path, "PUT", desired)
        if holder != POD_NAME:
            log("leadership_acquired", pod=POD_NAME)
        return True
    except Exception as update_exc:
        log("lease_update_failed", pod=POD_NAME, error=str(update_exc))
        return False


def vault_status(pod_ip):
    try:
        _, result = request(f"http://{pod_ip}:8200/v1/sys/seal-status")
        return result
    except Exception as exc:
        return {"error": str(exc)}


def unseal(pod_ip, keys):
    progress = None
    for key in keys:
        try:
            _, result = request(f"http://{pod_ip}:8200/v1/sys/unseal", "PUT", {"key": key})
            progress = result
            if not result.get("sealed", True):
                return result
        except Exception as exc:
            log("unseal_failed", pod_ip=pod_ip, error=str(exc))
            return progress or {"sealed": True}
    return progress or {"sealed": True}


def main():
    keys = [os.getenv(f"VAULT_UNSEAL_KEY_{i}") for i in range(1, 4)]
    keys = [key for key in keys if key]
    if AUTO_UNSEAL and len(keys) < 3:
        raise SystemExit("AUTO_UNSEAL requires VAULT_UNSEAL_KEY_1..3")
    remediation_count = 0
    window_started = time.time()
    log("started", namespace=NS, interval=INTERVAL, auto_unseal=AUTO_UNSEAL,
        allow_pod_delete=ALLOW_POD_DELETE)
    while True:
        try:
            if not leader_check():
                time.sleep(INTERVAL)
                continue
            pods = kube(f"/api/v1/namespaces/{NS}/pods?labelSelector=app.kubernetes.io/name=vault")
            ready = 0
            for pod in pods.get("items", []):
                name = pod["metadata"]["name"]
                phase = pod.get("status", {}).get("phase")
                ip = pod.get("status", {}).get("podIP")
                if phase == "Running" and ip:
                    ready += 1
                    status = vault_status(ip)
                    if status.get("sealed") and AUTO_UNSEAL:
                        log("sealed_detected", pod=name)
                        status = unseal(ip, keys)
                        log("unseal_result", pod=name, sealed=status.get("sealed"), progress=status.get("progress"))
                    log("pod_status", pod=name, phase=phase, sealed=status.get("sealed"), initialized=status.get("initialized"))
                else:
                    log("pod_not_ready", pod=name, phase=phase)
            if ready == 0:
                log("cluster_not_ready")
            if time.time() - window_started >= 3600:
                remediation_count, window_started = 0, time.time()
        except Exception as exc:
            log("reconcile_failed", error=str(exc))
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
