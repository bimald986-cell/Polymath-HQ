# Mind & Mythos Media Engine V2

## Objective
Mind & Mythos must produce real reviewable media end-to-end from a production command, without asking the owner to manually download, rename, or assemble generation assets.

## HQ governance
Horizon and the President Advisor may inspect and improve the M&M production system on review branches. Merge remains a President decision. The M&M concept, evidence standards, slow/warm voice direction, quality gates, and owner approval gate are authoritative.

## Architecture
M&M Director -> research -> proposal -> evidence-aware script -> scene plan -> provider selection -> online asset generation/retrieval -> narration/music -> captions -> edit -> Remotion/FFmpeg composition -> post-render QA -> verified review.mp4 -> four platform-specific packages -> owner review -> publishing adapter.

## OpenMontage harvest
Use bimald986-cell/openmontage as a reference/engine source for production manifests, provider selection, cinematic/documentary pipelines, Remotion composition, FFmpeg, subtitles, QA, checkpoints, decision logs, cost controls and fallbacks.

OpenMontage is AGPLv3. Do not silently paste its implementation into private HQ/M&M core. Preserve license/provenance. Prefer a separately licensed engine adapter or independent implementation of architecture/contracts. This matches `core/capability_registry.yaml`.

## Required behavior
- `Start production` means execute work, not write a hypothetical brief.
- Never output placeholders as completed artifacts.
- Never say `production complete` unless a physical final/review media file exists and passes validation.
- Provider failure triggers a valid fallback when available.
- Motion-required scenes must use real/generated motion, not silently substitute stills.
- Paid-provider use follows budget/approval policy.
- Public publishing requires explicit owner approval.
- Platform copy is generated separately for YouTube, TikTok, Instagram and Facebook.

## Provider families
Video: Runway, fal.ai gateways (Kling/Veo/MiniMax), HeyGen gateway, Pexels/Pixabay/Wikimedia/open footage, local video generation when configured, Remotion animated-media fallback.
Voice: ElevenLabs, Google TTS, OpenAI TTS, Piper fallback.
Music: configured AI music provider or licensed/royalty-free library.
Captions: Whisper/WhisperX/provider timestamps.
Composition: Remotion first for rich composition; FFmpeg for assembly/encoding/fallback.
QA: ffprobe, frame sampling, audio-level checks, subtitle validation, delivery-promise validation.

## Acceptance test
A production command for M&M 001 must end in one of two honest states:
1. `READY FOR OWNER REVIEW` with a playable verified `review.mp4` and four platform packages; or
2. `BLOCKED` with the exact missing provider/runtime/credential and no false completion claim.
