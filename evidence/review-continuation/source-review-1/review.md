# Separate scoped review — rejected working candidate

Reviewer: /root/startup_review, independent agent context, read-only.
Subject: exact runtime diff in rejected.patch, based on v0.1.0 (with plan commit d9276da).
Verdict: rejected; no integration authorized by this review.

Requirement: missing/invalid review must remain recoverable through review_only.
Reproduction: recovery_kind({}, {}, {}, None), list or string raises AttributeError
at review.get. require_gate first closes, then recovery_kind and self.review.get
crash instead of maintaining a resumable wait.
Consequence: workflow task failure, no usable review-only continuation.
Requested correction: handle non-object evidence throughout this branch and test
it natively. No other concrete blocker identified in scoped reading. Final review
must cover exact committed source and focused evidence.
