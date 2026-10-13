import { Brand } from './brand'
import { navigate } from './routes'

function SafariShareIcon() {
  return (
    <img
      class="install-share-icon"
      src="/install/share-rounded.png"
      width={30}
      height={30}
      alt=""
      aria-hidden="true"
    />
  )
}


export function Install() {
  return (
    <>
      <Brand />
      <div class="title-bar">
        <h1 class="title">Add to Home Screen</h1>
        <button type="button" class="text-btn" onClick={() => navigate({ name: 'home' })}>
          Back to decks
        </button>
      </div>
      <p class="lede">
        Save a Home Screen shortcut so you can open juzi like an app icon.
      </p>

      <section class="install-section" aria-labelledby="install-steps-heading">
        <h2 id="install-steps-heading" class="install-heading">
          Steps
        </h2>
        <p class="install-note">On an iPhone or iPad, use Safari.</p>
        <ol class="install-steps">
          <li>Open juzi in Safari.</li>
          <li>
            Tap the Share button <SafariShareIcon />.
          </li>
          <li>Scroll and tap Add to Home Screen.</li>
          <li>Tap Add.</li>
        </ol>
      </section>

      <section class="install-section" aria-labelledby="install-faq-heading">
        <h2 id="install-faq-heading" class="install-heading">
          FAQ
        </h2>
        <h3 class="install-question">Does this install a native app?</h3>
        <p class="install-answer">
          No. It adds a Home Screen shortcut that opens the same juzi website in a
          full-screen window.
        </p>
        <h3 class="install-question">Does juzi collect device data from this?</h3>
        <p class="install-answer">
          No. Add to Home Screen does not give juzi access to your device or new
          personal data. You still sign in with your usual account.
        </p>
        <h3 class="install-question">Why add it?</h3>
        <p class="install-answer">
          Quicker to open, and you skip Safari browser chrome while you study.
        </p>
      </section>

      <p class="install-icon-credit">
        Share icon by{' '}
        <a href="https://icons8.com/icon/97424/share-rounded" rel="noopener noreferrer">
          Icons8
        </a>
        .
      </p>
    </>
  )
}
