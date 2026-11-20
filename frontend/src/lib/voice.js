/** The agent's voice, chosen when it is created. The server maps male -> aura-2-draco-en and female ->
 * aura-2-pandora-en (both British English) and uses it on every call the agent makes. */
export const VOICES = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]
export const voiceLabel = (voice) => VOICES.find((v) => v.value === voice)?.label ?? ''
