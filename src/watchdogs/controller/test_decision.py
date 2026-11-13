import unittest

from decision import Action, ClusterObservation, PodObservation, choose_decision


def healthy_pod(name):
    return PodObservation(name, "Running", True, sealed=False)


class DecisionTests(unittest.TestCase):
    def base(self, pods, **kwargs):
        values = {
            "pods": pods,
            "expected_replicas": len(pods),
            "quorum_healthy": True,
            "statefulset_identity_verified": True,
        }
        values.update(kwargs)
        return ClusterObservation(**values)

    def test_healthy_cluster_is_noop(self):
        result = choose_decision(self.base([healthy_pod("vault-0")]), auto_unseal=False, allow_pod_delete=False)
        self.assertEqual(result.action, Action.NOOP)

    def test_unhealthy_pod_with_healthy_pvc_can_restart_only_when_enabled(self):
        pod = PodObservation("vault-1", "Pending", False, sealed=False)
        observation = self.base([healthy_pod("vault-0"), pod])
        blocked = choose_decision(observation, auto_unseal=False, allow_pod_delete=False)
        allowed = choose_decision(observation, auto_unseal=False, allow_pod_delete=True)
        self.assertEqual(blocked.action, Action.REQUIRE_APPROVAL)
        self.assertEqual(allowed.action, Action.RESTART_POD)

    def test_pvc_uncertainty_never_becomes_pod_or_pvc_delete(self):
        pod = PodObservation("vault-1", "Pending", False, sealed=False, pvc_healthy=False)
        result = choose_decision(self.base([healthy_pod("vault-0"), pod]), auto_unseal=False, allow_pod_delete=True)
        self.assertEqual(result.action, Action.OBSERVE)

    def test_pvc_recovery_requires_backup_and_approval(self):
        pod = PodObservation("vault-1", "Pending", False, sealed=False, pvc_healthy=False)
        observation = self.base([healthy_pod("vault-0"), pod], backup_verified=True)
        result = choose_decision(
            observation,
            auto_unseal=False,
            allow_pod_delete=True,
            allow_pvc_delete=True,
        )
        self.assertEqual(result.action, Action.REQUIRE_APPROVAL)
        self.assertFalse(result.safe_to_automate)

    def test_quorum_failure_fails_closed(self):
        result = choose_decision(
            self.base([healthy_pod("vault-0"), healthy_pod("vault-1")], quorum_healthy=False),
            auto_unseal=True,
            allow_pod_delete=True,
        )
        self.assertEqual(result.action, Action.OBSERVE)

    def test_sealed_pod_requires_unseal_policy(self):
        sealed = PodObservation("vault-0", "Running", True, sealed=True)
        observation = self.base([sealed])
        blocked = choose_decision(observation, auto_unseal=False, allow_pod_delete=False)
        allowed = choose_decision(observation, auto_unseal=True, allow_pod_delete=False)
        self.assertEqual(blocked.action, Action.REQUIRE_APPROVAL)
        self.assertEqual(allowed.action, Action.UNSEAL)


if __name__ == "__main__":
    unittest.main()
