import { usePageData } from '../../api/pageData'
import { Callout, Card, EmptyState, Loading } from '../../kit'
import type { QualityData } from '../../types'
import AvailabilitySection from './quality/AvailabilitySection'
import BenchmarkSection from './quality/BenchmarkSection'
import CalibrationSection from './quality/CalibrationSection'
import DecompositionSection from './quality/DecompositionSection'
import HoldoutSection from './quality/HoldoutSection'
import MissesSection from './quality/MissesSection'
import NewsShadowSection from './quality/NewsShadowSection'
import PensSection from './quality/PensSection'
import ScatterSection from './quality/ScatterSection'

// v19h §2.1: what is left here is the layout — one read, the status split
// `Loaded` spells, and the order the cards appear in. Every prop-taking
// section moved to `quality/`, so this file reads as the shape of the tab.
export default function QualityTab() {
  // v18e §2.3. Four sections below keep their own reads, each where it lives;
  // this one is the tab's own. The status split it made by hand — a 422 is
  // "nothing has been evaluated yet" and the server's own sentence says what
  // to run — is `Loaded`'s, spelt in its words.
  const page = usePageData<QualityData>('/api/quality')
  const absent = page.status === 404 || page.status === 422

  if (page.error !== null && !absent) {
    return (
      <Card title="Quality unavailable">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  if (page.error !== null) {
    return (
      <EmptyState
        title="Nothing evaluated yet"
        detail={page.error}
        action="gaffer evaluate"
      />
    )
  }
  const data = page.data
  if (!data) return <Loading />

  return (
    <>
      {data.current && <HoldoutSection current={data.current} />}
      {data.benchmark && <BenchmarkSection benchmark={data.benchmark} />}
      {data.decomposition
        && <DecompositionSection decomposition={data.decomposition} />}
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
      {/* A9: deliberately not the news-shadow rule above. The card renders
          whenever either key is present, empty report included, because spec
          §1 wants the page to say what it is waiting for. `rows > 0` gates
          the tables inside it, not the card. */}
      {(data.flag_latency || data.presser_grades)
        && <AvailabilitySection flag={data.flag_latency ?? null}
                                presser={data.presser_grades ?? null} />}
      <CalibrationSection />
      <ScatterSection />
      <MissesSection />
      <PensSection />
    </>
  )
}
