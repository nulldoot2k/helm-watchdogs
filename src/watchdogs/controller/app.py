#!/usr/bin/env python3
import json
import os
import ssl
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from decision import Action, ClusterObservation, PodObservation, choose_decision
from api.server import create_server as create_api_server
import urllib.error
import urllib.request


NS = os.getenv("WATCHDOG_NAMESPACE", "vault")
LEASE_NS = os.getenv("LEASE_NAMESPACE", os.getenv("POD_NAMESPACE", "helm-watchdogs"))
POD_NAME = os.getenv("POD_NAME", "unknown")
LEASE_NAME = os.getenv("LEASE_NAME", "helm-watchdogs-leader")
VAULT_SERVICE = os.getenv("VAULT_SERVICE", "vault-active")
VAULT_STATEFULSET = os.getenv("VAULT_STATEFULSET", "vault")
INTERVAL = int(os.getenv("WATCHDOG_INTERVAL_SECONDS", "10"))
AUTO_UNSEAL = os.getenv("AUTO_UNSEAL", "false").lower() == "true"
ALLOW_POD_DELETE = os.getenv("ALLOW_POD_DELETE", "false").lower() == "true"
MAX_REMEDIATIONS = int(os.getenv("MAX_REMEDIATIONS_PER_HOUR", "3"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "8080"))
API_PORT = int(os.getenv("API_PORT", "8081"))
API_TOKEN_FILE = os.getenv("WATCHDOGS_API_TOKEN_FILE", "")
API_ENABLED = os.getenv("API_ENABLED", "true").lower() == "true"
UI_ENABLED = os.getenv("UI_ENABLED", "false").lower() == "true"

METRICS = {
    "reconcile_total": 0,
    "reconcile_failed_total": 0,
    "vault_pods_observed": 0,
    "vault_pods_sealed": 0,
    "leadership_acquired_total": 0,
}
METRICS_LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
STATE = {
    "status": "starting",
    "vault": {"status": "unknown"},
    "incidents": [],
    "audit": [],
    "diagnostics": {"component": "controller"},
}


def metric_inc(name, value=1):
    with METRICS_LOCK:
        METRICS[name] = METRICS.get(name, 0) + value


def state_snapshot():
    with STATE_LOCK:
        return json.loads(json.dumps(STATE))


def update_state(**fields):
    with STATE_LOCK:
        STATE.update(fields)


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        elif self.path == "/metrics":
            with METRICS_LOCK:
                values = dict(METRICS)
            lines = [
                "# HELP watchdogs_info Helm Watchdogs controller information.",
                "# TYPE watchdogs_info gauge",
                'watchdogs_info{component="controller"} 1',
            ]
            for name, value in sorted(values.items()):
                lines.append(f"watchdogs_{name} {value}")
            body = ("\n".join(lines) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        else:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def start_metrics_server():
    server = ThreadingHTTPServer(("0.0.0.0", METRICS_PORT), MetricsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()


def start_api_server():
    server = create_api_server("0.0.0.0", API_PORT, API_TOKEN_FILE, state_snapshot, UI_ENABLED)
    threading.Thread(target=server.serve_forever, daemon=True).start()


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
            metric_inc("leadership_acquired_total")
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
            metric_inc("leadership_acquired_total")
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


def pod_is_ready(pod):
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in pod.get("status", {}).get("conditions", [])
    )


def statefulset_observation():
    try:
        result = kube(f"/apis/apps/v1/namespaces/{NS}/statefulsets/{VAULT_STATEFULSET}")
        replicas = int(result.get("spec", {}).get("replicas", 0))
        selector = result.get("spec", {}).get("selector", {}).get("matchLabels", {})
        identity_verified = bool(selector)
        return replicas, identity_verified
    except Exception as exc:
        log("statefulset_observation_failed", statefulset=VAULT_STATEFULSET, error=str(exc))
        return 0, False


def main():
    start_metrics_server()
    if API_ENABLED:
        start_api_server()
    remediation_count = 0
    window_started = time.time()
    log("started", namespace=NS, interval=INTERVAL, auto_unseal=AUTO_UNSEAL,
        allow_pod_delete=ALLOW_POD_DELETE)
    update_state(status="observing")
    while True:
        metric_inc("reconcile_total")
        try:
            if not leader_check():
                time.sleep(INTERVAL)
                continue
            pods = kube(f"/api/v1/namespaces/{NS}/pods?labelSelector=app.kubernetes.io/name=vault")
            ready = 0
            metric_inc("vault_pods_observed", len(pods.get("items", [])))
            expected_replicas, identity_verified = statefulset_observation()
            observations = []
            live_pods = {}
            for pod in pods.get("items", []):
                name = pod["metadata"]["name"]
                phase = pod.get("status", {}).get("phase")
                ip = pod.get("status", {}).get("podIP")
                if phase == "Running" and ip:
                    status = vault_status(ip)
                    is_ready = pod_is_ready(pod)
                    ready += int(is_ready)
                    if status.get("sealed"):
                        metric_inc("vault_pods_sealed")
                    observations.append(PodObservation(
                        name=name,
                        phase=phase,
                        ready=is_ready,
                        sealed=status.get("sealed"),
                        identity_verified=identity_verified,
                    ))
                    live_pods[name] = (ip, status)
                    log("pod_status", pod=name, phase=phase, ready=is_ready,
                        sealed=status.get("sealed"), initialized=status.get("initialized"))
                else:
                    observations.append(PodObservation(
                        name=name,
                        phase=phase or "Unknown",
                        ready=False,
                        identity_verified=identity_verified,
                    ))
                    log("pod_not_ready", pod=name, phase=phase)
            majority = expected_replicas // 2 + 1 if expected_replicas else 0
            decision = choose_decision(
                ClusterObservation(
                    pods=observations,
                    expected_replicas=expected_replicas,
                    quorum_healthy=ready >= majority > 0,
                    statefulset_identity_verified=identity_verified,
                ),
                auto_unseal=AUTO_UNSEAL,
                allow_pod_delete=ALLOW_POD_DELETE,
            )
            log("recovery_decision", action=decision.action.value, target=decision.target,
                reason=decision.reason, safe_to_automate=decision.safe_to_automate)
            update_state(
                status="healthy" if decision.action == Action.NOOP else "degraded",
                vault={
                    "namespace": NS,
                    "service": VAULT_SERVICE,
                    "ready_pods": ready,
                    "expected_replicas": expected_replicas,
                    "decision": decision.action.value,
                },
                diagnostics={
                    "last_reason": decision.reason,
                    "safe_to_automate": decision.safe_to_automate,
                },
            )
            if decision.action == Action.UNSEAL and decision.target in live_pods:
                log("sealed_detected", pod=decision.target,
                    action="delegated_to_native_watchdogs_seal")
            if ready == 0:
                log("cluster_not_ready")
            if time.time() - window_started >= 3600:
                remediation_count, window_started = 0, time.time()
        except Exception as exc:
            metric_inc("reconcile_failed_total")
            update_state(status="unknown", diagnostics={"error": str(exc)})
            log("reconcile_failed", error=str(exc))
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
