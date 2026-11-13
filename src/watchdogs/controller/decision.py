"""Deterministic, data-protective recovery decisions for the Vault integration.

This module has no Kubernetes or Vault client dependencies. It turns an
observed snapshot into a bounded decision so the policy can be tested without
mutating a cluster.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class Action(str, Enum):
    OBSERVE = "observe"
    RESTART_POD = "restart_pod"
    UNSEAL = "unseal"
    REQUIRE_APPROVAL = "require_approval"
    NOOP = "noop"


@dataclass(frozen=True)
class PodObservation:
    name: str
    phase: str
    ready: bool
    sealed: bool | None = None
    identity_verified: bool = True
    pvc_healthy: bool = True


@dataclass(frozen=True)
class ClusterObservation:
    pods: Sequence[PodObservation] = field(default_factory=tuple)
    expected_replicas: int = 0
    quorum_healthy: bool = False
    backup_verified: bool = False
    statefulset_identity_verified: bool = False


@dataclass(frozen=True)
class Decision:
    action: Action
    target: str | None
    reason: str
    safe_to_automate: bool


def choose_decision(
    observation: ClusterObservation,
    *,
    auto_unseal: bool,
    allow_pod_delete: bool,
    allow_pvc_delete: bool = False,
) -> Decision:
    """Choose the smallest safe action and fail closed on uncertainty."""

    pods = tuple(observation.pods)
    if not pods or observation.expected_replicas < 1:
        return Decision(Action.OBSERVE, None, "cluster_inventory_incomplete", False)

    if any(not pod.identity_verified for pod in pods):
        return Decision(Action.OBSERVE, None, "pod_identity_uncertain", False)

    if len(pods) < observation.expected_replicas:
        return Decision(Action.OBSERVE, None, "pod_inventory_incomplete", False)

    if not observation.quorum_healthy:
        return Decision(Action.OBSERVE, None, "raft_quorum_not_healthy", False)

    sealed = next((pod for pod in pods if pod.sealed is True), None)
    if sealed:
        if auto_unseal:
            return Decision(Action.UNSEAL, sealed.name, "sealed_pod_with_verified_cluster", True)
        return Decision(Action.REQUIRE_APPROVAL, sealed.name, "sealed_pod_auto_unseal_disabled", False)

    unhealthy = [pod for pod in pods if pod.phase != "Running" or not pod.ready]
    if not unhealthy:
        return Decision(Action.NOOP, None, "cluster_healthy", True)

    candidate = unhealthy[0]
    if not observation.statefulset_identity_verified:
        return Decision(Action.OBSERVE, candidate.name, "statefulset_identity_uncertain", False)

    if not candidate.pvc_healthy:
        if allow_pvc_delete and observation.backup_verified:
            return Decision(Action.REQUIRE_APPROVAL, candidate.name, "pvc_recovery_requires_explicit_approval", False)
        return Decision(Action.OBSERVE, candidate.name, "pvc_health_uncertain_protect_data", False)

    if allow_pod_delete:
        return Decision(Action.RESTART_POD, candidate.name, "single_pod_unhealthy_pvc_healthy", True)
    return Decision(Action.REQUIRE_APPROVAL, candidate.name, "pod_restart_disabled_by_policy", False)
