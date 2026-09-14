# Timed attack rewards

The event overlay at 33%, 66%, and 100% pauses battle input while its countdown
automatically picks a reward. The bot verifies that it disappears before resuming.
No OCR or reward-card click is needed. Stop interrupts the wait.

The main strategy's End Battle and Surrender rules remain unchanged. The bot does
not wait for later milestones. Final damage can advance during exit confirmation.
Hero abilities retain their stored deployment slots; only a reward interruption
requires relocating the live hero portrait if the troop bar moves.

Validation: `python -m unittest discover -s tests -v`.
Live validation on Google Play Games at 1299×731 confirmed four hero ability clicks,
automatic reward selection after roughly 12 seconds, and battle exit after passing
50% (55% on the results screen). Later milestones are covered by repeat-overlay
tests; this live test did not prolong the attack to reach them.
