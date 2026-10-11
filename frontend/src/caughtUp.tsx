type CaughtUpProps = {
  onBack: () => void
}

export function CaughtUp({ onBack }: CaughtUpProps) {
  return (
    <section class="caught-up">
      <h1 class="caught-up-title">All caught up</h1>
      <p class="caught-up-copy">No cards are due in this deck right now.</p>
      <div class="picker-actions">
        <button type="button" class="cta" onClick={onBack}>
          Back to decks
        </button>
      </div>
    </section>
  )
}
