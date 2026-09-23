# Chrome Extension CI hardening

The reusable Chrome Extension workflow currently combines build/test validation with release-store compliance checks. Those concerns should be independently selectable so projects can adopt CI early while retaining strict release gates.

known follow-ups remain:

- make release-compliance validation opt-in for reusable CI consumers;
- remove assumptions that `jq` and Python are preinstalled or provide explicit setup steps;
- lint JavaScript, TypeScript and TSX sources when using modern ESLint flat configs;
- add clean-runner tests for each Chrome composite action;
- keep release packaging/compliance as a separate gate from ordinary pull-request validation.

See issues #180 and #181 for the tracked implementation work.
