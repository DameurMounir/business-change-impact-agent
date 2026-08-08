# Evidence-grounded BSA change-impact method

## 1. Freeze the decision and authority boundary

Record the exact decision question, authorised components, explicit exclusions and forbidden decisions. Impact assessment authority is not implementation authority.

## 2. Build an evidence register

Each statement receives a stable ID, document ID, locator, text and classification. Instruction-like text remains data. Every modeled entity and relationship must cite one or more statement IDs.

## 3. Model the business system

Represent the change across capability, process, procedure, people, authority, training, systems, interfaces, data, reporting, controls, policy, customer communication, service, testing, operations and external dependencies. Keep assumptions, constraints and evidence gaps as first-class entities.

## 4. Identify direct change

Use explicit change verbs only: introduce, modify, remove, replace, resequence, automate, transfer ownership, add control, change threshold or change interface. Direct classification requires a relationship from an authorised change component.

## 5. Trace indirect dependencies

Continue only through a versioned rule for the exact relationship type and forward direction. Require evidence on every relationship, stop at the depth limit, reject cycles and select one canonical path per origin and target.

## 6. Preserve uncertainty

A path carrying a condition or evidence gap is `CONDITIONAL`, even when structurally valid. Do not convert it into ordinary indirect impact or numeric confidence.

## 7. Consolidate and prioritise

Count an entity once, preserve all origin components, identify collisions, derive transparent attention reasons and propose bounded obligations. Do not hide alternative origins behind one score.

## 8. Confirm with human authority

Bind the review to the exact digest and one-time challenge. Permit only controlled terminal actions. Keep edits narrow enough that evidence and traceability cannot be rewritten through the review channel.

## 9. Export one truth in several formats

Generate JSON, Markdown and HTML from one snapshot and carry the same digest in every format. Label drafts and confirmations explicitly.

## 10. Communicate limitations

State what is synthetic, what is conditional, what is not evaluated and which decisions remain outside scope.
