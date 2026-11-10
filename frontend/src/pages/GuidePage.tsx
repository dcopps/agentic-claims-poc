import { Link } from 'react-router-dom'
import { Card } from '../components/ui'
import { guideCopy, guideLinks, type GuideSegment } from '../copy/guide'
import { typography } from '../styles/tokens'

// The first-time visitor's page: what the system is, how it works, how to try
// it, the three scenarios and what each should do, how to read a run page, and
// where the public documents are. All text lives in copy/guide.ts.
export function GuidePage() {
  return (
    <div className="space-y-4">
      <h1 className={typography.pageTitle}>{guideCopy.title}</h1>

      <Card title={guideCopy.whatHeading}>
        <div className="space-y-2 text-sm text-slate-700">
          <p>{guideCopy.whatIntro}</p>
          <ul className="list-disc space-y-1 pl-5" aria-label="The four agents">
            {guideCopy.agents.map((agent) => (
              <li key={agent.name}>
                <span className="font-medium">{agent.name}</span> {agent.detail}
              </li>
            ))}
          </ul>
          <p>{guideCopy.whatRules}</p>
          <p>{guideCopy.whatScope}</p>
        </div>
      </Card>

      <Card title={guideCopy.howHeading}>
        <div className="space-y-2 text-sm text-slate-700">
          {guideCopy.how.map((part) => (
            <p key={part.lead}>
              <span className="font-medium">{part.lead}</span> {part.body}
            </p>
          ))}
        </div>
      </Card>

      <Card title={guideCopy.tryHeading}>
        <ol
          className="list-decimal space-y-1 pl-5 text-sm text-slate-700"
          aria-label="Try it steps"
        >
          {guideCopy.trySteps.map((step, index) => (
            <li key={index}>
              <Sentence segments={step} />
            </li>
          ))}
        </ol>
        <div className="mt-3 space-y-1 text-sm text-slate-700">
          {guideCopy.tryMore.map((sentence, index) => (
            <p key={index}>
              <Sentence segments={sentence} />
            </p>
          ))}
        </div>
      </Card>

      <Card title={guideCopy.scenariosHeading}>
        <ul className="space-y-1 text-sm text-slate-700">
          {guideCopy.scenarios.map((scenario) => (
            <li key={scenario.name}>
              <span className="font-medium">{scenario.name}</span>: {scenario.detail}
            </li>
          ))}
        </ul>
      </Card>

      <Card title={guideCopy.runPageHeading}>
        <p className="text-sm text-slate-700">{guideCopy.runPage}</p>
      </Card>

      <Card title={guideCopy.linksHeading}>
        <ul className="space-y-1 text-sm" aria-label="Guide links">
          {guideLinks.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="text-blue-700 hover:underline"
              >
                {link.label}
              </a>
              <span className="text-slate-500"> — {link.detail}</span>
            </li>
          ))}
          <li>
            <Link to="/integrations" className="text-blue-700 hover:underline">
              {guideCopy.integrationsLink}
            </Link>
          </li>
        </ul>
      </Card>
    </div>
  )
}

// One "Try it" sentence: plain text as written, the interface's labels in <em>
// so a reader can tell a button name from the surrounding words.
function Sentence({ segments }: { segments: readonly GuideSegment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        typeof segment === 'string' ? (
          <span key={index}>{segment}</span>
        ) : (
          <em key={index}>{segment.label}</em>
        ),
      )}
    </>
  )
}
