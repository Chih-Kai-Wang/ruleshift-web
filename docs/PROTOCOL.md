# RuleShift v1 protocol

This document must be frozen before the confirmatory test run. Changes after looking at test outcomes require a new protocol and a fresh held-out evaluation, never replacement of old results.

## Question
Can evidence-scoped memory invalidation improve the success/cost tradeoff under changing business rules? All model weights remain frozen. This is a study of agent memory policies, not weight-based continual learning.

## World
Three task families: fulfillment, address changes, returns. Four templates per family: two development, one validation, one test. Development, validation and test use distinct policy parameter combinations. Eight tasks form one persistent stream. Rule schedules: stable, one returns change at task 3, returns then shipping/change changes at tasks 3 and 5, and all rules A→B→A at tasks 3 and 6 (zero-based). This schedule is never included in agent inputs. State changes through transactional tools; business rules are enforced by the world. Invalid operations consume budget but cannot corrupt state.

Initial policy observations are shared, fixed warmup evidence available equally to all memory strategies. Every paired stream starts at the same snapshot. Task inputs and event schedules are fixed independently of agent actions; actions persist and consume stock. A stream is the statistical unit. Evaluator state, future events, seeds, template split and hidden truth are not available to the model.

## Policies
`none`: no cross-task memory. `retrieval`: latest observed policy evidence per scope, no automatic refresh. `ttl`: discard evidence after two task boundaries. `refresh`: fetch current policy for the active scope at the start of every task. `selective`: retrieve scoped evidence; a tool policy-block signal marks that scope stale and triggers a re-read before the next model decision. Refresh and selective reads consume the same tool budget and their contents enter model input. All policies can use all tools and override their memory by requesting a policy read themselves. No policy receives hidden version/epoch change notifications. The selective strategy is an explicit engineered heuristic, not an emergent learning algorithm.

## Limits and inference
Same model and pinned weights, greedy decoding, maximum 12 world-tool calls/task, maximum 1024 tokenizer-measured cross-task memory tokens, maximum 180 generated tokens/model response. Parsing failures consume an attempt; a separate 16 model-attempt cap prevents infinite malformed-output retries. Entire task cost includes policy reads, prompt and completion tokens, and model/tool elapsed time. No LLM judge or simulated LLM world responses.

## Evaluation
Primary task success requires the correct final decision AND exact required state effects, assessed by an independent reference specification. A rejection must be justified by an actual policy/stock restriction. Merely claiming success or not acting is insufficient. Independent reference runs must solve all generated tasks before model evaluation.

Test matrix: 4 schedules × 5 seeds × 8 tasks × 5 policies = 800 model-driven task runs. Test templates and policy combinations are not used to tune prompts or policies. Development smoke: 2 schedules × 1 seed × 4 tasks × 2 policies = 16 task runs. Validation confirms executability only; do not tune against held-out test scores. Model failures and malformed outputs remain in the denominator. Infrastructure failures are resumable and separately logged.

Report paired stream differences with a 95% bootstrap interval across the 20 stream pairs, not across 800 dependent tasks; per-schedule estimates have only five seeds and are exploratory. Primary comparison is selective vs refresh (success and total token/tool cost). Also report unchanged-scope success, decision errors consistent with stale observed policy, illegal action attempts, query costs and recovery after each change. Recovery is the number of affected tasks through the first successful one; unobserved recovery is right-censored, never silently removed.

## Limits
Synthetic retail, small model, few seeds, deterministic schedules and enforced business rules do not establish production readiness or general agent intelligence. The first 4B experiment is a pilot-scale study even when the complete predefined matrix is run. Software correctness does not depend on a favorable research result.

