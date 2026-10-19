// npm audit gate for CI: fails on any high or critical advisory in <dir>'s dependency tree, except those listed
// here with a reason. Usage: node scripts/npm-audit.mjs frontend
import { execFileSync } from 'node:child_process'

// Advisory → why it is accepted, and when to look again. Keep this list empty whenever possible.
const ACCEPTED = {
  'GHSA-vfj7-8cjw-p6xm': 'braces <=3.0.3 (stack-exhaustion DoS on nested patterns). No fixed release exists. It is ' +
    'reached only through build and test tooling (tailwindcss 3, chokidar in firebase-tools), which only ever expands ' +
    "patterns from this repo's own config, never user input, and none of it ships in the app bundle. " +
    'Revisit when braces publishes a fix or on the move to Tailwind 4.',
}

const dir = process.argv[2] || '.'
let report
try {
  report = JSON.parse(execFileSync('npm', ['audit', '--json'], { cwd: dir, encoding: 'utf8', maxBuffer: 64 << 20 }))
} catch (e) {
  report = JSON.parse(e.stdout)        // npm audit exits non-zero when it finds anything
}
const advisories = new Map()
for (const [name, v] of Object.entries(report.vulnerabilities || {})) {
  for (const via of v.via) {
    if (typeof via === 'object' && ['high', 'critical'].includes(via.severity)) {
      advisories.set(via.url.split('/').pop(), `${via.severity} ${name} ${via.range}: ${via.title}`)
    }
  }
}
const failing = [...advisories].filter(([id]) => !ACCEPTED[id])
for (const [id, text] of advisories) console.log(`${ACCEPTED[id] ? 'accepted' : 'FAIL    '} ${id} ${text}`)
if (failing.length) {
  console.error(`\n${failing.length} high/critical advisories in ${dir}. Upgrade, or add them to ACCEPTED with a reason.`)
  process.exit(1)
}
console.log(`npm audit ${dir}: no unaccepted high or critical advisories`)
