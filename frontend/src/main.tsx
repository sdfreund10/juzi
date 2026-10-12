import { initializeMonitoring } from './monitoring'
import { render } from 'preact'
import './index.css'
import { App } from './app.tsx'
import { registerServiceWorker } from './registerServiceWorker.ts'

initializeMonitoring()

render(<App />, document.getElementById('app')!)
registerServiceWorker()
