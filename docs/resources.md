# Resource routing for agents

This is a **routing catalog**, not a bundled code library. Use it to find the
smallest set of primary documentation, examples, and specialist capabilities
that materially improve the current surface. Do not download a framework,
component catalog, snippet collection, or skill merely because it appears here.

## Use resources deliberately

For a new task:

1. State the user-visible outcome, active surface, and quality oracle in the
   issue or `Local-WAL` draft.
2. Search the already-reviewed local skills and current project dependencies
   first. A verified skill is a reusable capability, not disposable advice;
   keep it when it remains trusted and relevant, and update its review record
   when the source changes.
3. If a capability or design decision is missing, use the official source map
   below. Prefer current documentation and first-party examples over search
   snippets or influencer checklists.
4. Before copying code, examples, assets, fonts, icons, or templates, check the
   source repository's current license, terms, version, dependencies, security
   notes, and attribution requirements. Record the source/revision or digest in
   the issue and, for a skill, in `project.toml`.
5. Implement the smallest relevant idea in the project's chosen stack. Run the
   real artifact oracle and the focused regression; do not report a copied
   example as product evidence.

The useful question is not “Which popular library should I install?” It is
“Which reviewed capability or primary source closes this named gap, under what
license, with what rollback and quality evidence?”

## First-party resource map

Choose the row that matches the active surface. These links are starting points;
the page's current version and terms still govern use.

| Trigger | Start here | What to verify before adopting |
|---|---|---|
| Web application structure and components | [React documentation](https://react.dev/learn), [MDN Web Docs](https://developer.mozilla.org/en-US/) | Version, browser/runtime support, accessibility, and the actual interaction path. |
| Utility-first styling | [Tailwind CSS documentation](https://tailwindcss.com/docs) and [Tailwind repository/license](https://github.com/tailwindlabs/tailwindcss/blob/main/LICENSE) | Compatibility with the chosen framework, generated CSS behavior, contrast, focus states, and bundle/runtime cost. |
| Composable web components | [shadcn/ui documentation](https://ui.shadcn.com/docs) and [shadcn/ui repository](https://github.com/shadcn-ui/ui) | Current component code, copy/build model, dependencies, and the repository license; do not assume a registry item is production-ready. |
| React Native app | [React Native introduction](https://reactnative.dev/docs/getting-started), [architecture guide](https://reactnative.dev/docs/architecture), and [testing overview](https://reactnative.dev/docs/testing-overview) | Supported version, native modules, device/emulator evidence, permissions, release behavior, and performance. |
| Expo-managed mobile workflow | [Expo documentation](https://docs.expo.dev/) and [store-submission guidance](https://docs.expo.dev/submit/introduction/) | EAS/build credentials, native versus web behavior, OTA/update policy, and platform review requirements. |
| Apple app UI and submission | [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/) and [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) | Current platform, region, entitlements, review notes, live backend, permissions, payments, account/login, and screenshot parity. |
| Android app UI and release | [Android developer documentation](https://developer.android.com/) and [Google Play policy center](https://support.google.com/googleplay/android-developer/answer/9899233) | Current target API, device behavior, content/data declarations, payments, account deletion, and release policy. |
| Accessibility and inclusive UI | [W3C WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/), [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) | The project's chosen conformance target, keyboard/screen-reader path, and tested user journey; a scanner is not a conformance claim. |
| Web security and privacy | [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/) and [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework) | Threats, data flows, deployment/provider behavior, and current advisories; a checklist is not an assessment. |
| Video/audio pipelines | [FFmpeg documentation](https://ffmpeg.org/documentation.html) | Codec/container/license compatibility, reproducibility, media size, and an actual playback/export check. |
| Blender/3D pipelines | [Blender Manual](https://docs.blender.org/manual/en/latest/) | Version, add-on/source provenance, render settings, hardware limits, and a rendered artifact. |

A resource is evidence only after the project records what was consulted and
what was actually adopted. The current research note at
[`research/primary-source-hardening-2026-09-25.md`](./research/primary-source-hardening-2026-09-25.md)
contains the provenance boundary for this template.

## Skill and example acceptance gate

A candidate skill, snippet, template, or asset is eligible for a project only
when the issue records:

- the trigger and the missing capability;
- publisher/source, version or immutable revision, and license;
- exact files and dependencies it would introduce;
- permissions, network destinations, install scripts, and data access;
- security/privacy review and a rollback action;
- a focused disposable trial and the real-artifact oracle;
- the resulting project-local decision, which may be “do not adopt.”

Retain a verified capability for future reuse when it remains useful. Remove or
disable it when its source is no longer trusted, its permissions are excessive,
its maintenance state is unacceptable, or the project owner chooses to retire
it. “No current task uses it” is not, by itself, a reason to delete it.

For code copied from an example, preserve required attribution and licensing
notice, adapt it to the project's conventions, and add a regression/quality
check. A screenshot or generated UI is not permission to copy its underlying
code or assets.

## Platform-review and legal-risk prompt

Use this when an app, website, payment flow, AI feature, user-generated content,
or account system may face store or regulatory review:

> Before public submission, enumerate the applicable platform, jurisdiction,
> user, payment, account, permission, privacy, AI, UGC, and age-related facts.
> For each fact, link an official platform/regulator source and attach observed
> evidence: review notes and demo access, live backend behavior, permission
> purpose strings, data inventory/retention, account export/deletion path,
> moderation/takedown path, and screenshot/live parity. Mark unknowns as
> `pending` and route them to the owner/counsel; do not convert a checklist,
> code scan, or model claim into compliance.

Useful primary references include Apple's [Before You Submit and App Review
Guidelines](https://developer.apple.com/app-store/review/guidelines/), Apple's
[Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/),
the [FTC privacy and security guidance](https://www.ftc.gov/business-guidance/privacy-security),
the [UK ICO data-protection guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/),
and the [U.S. Copyright Office DMCA](https://www.copyright.gov/dmca/) portal.

These sources do not make a universal checklist. Payment/IAP, external-link,
Sign in with Apple, account-deletion, AI disclosure, UGC, and marketing-email
obligations vary by platform, region, product, age policy, and distribution
model. A fixed fine, damage amount, or “you will be rejected” claim from a
social post is not a legal source. Verify current primary guidance and obtain
qualified review for the actual facts; do not paste exploit details, personal
data, or confidential provider material into a public issue.
