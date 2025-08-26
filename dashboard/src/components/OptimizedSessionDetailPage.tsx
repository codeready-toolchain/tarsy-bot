
import SessionDetailPageBase from './SessionDetailPageBase';
import TechnicalTimeline from './TechnicalTimeline';
import type { DetailedSession } from '../types';

/**
 * Technical session detail page
 * Uses the shared SessionDetailPageBase with technical timeline rendering
 */
function OptimizedSessionDetailPage() {
  // Timeline component factory for technical view
  const renderTechnicalTimeline = (session: DetailedSession, useVirtualization?: boolean) => (
    <TechnicalTimeline 
      session={session} 
      useVirtualization={useVirtualization} 
    />
  );

  return (
    <SessionDetailPageBase
      viewType="technical"
      timelineComponent={renderTechnicalTimeline}
    />
  );
}

export default OptimizedSessionDetailPage;
