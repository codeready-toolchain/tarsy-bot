import { useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { SessionProvider } from '../contexts/SessionContext';
import SessionDetailPageBase from './SessionDetailPageBase';
import ConversationTimeline from './ConversationTimeline';
import TechnicalTimeline from './TechnicalTimeline';
import ScoreDetailView from './ScoreDetailView';
import { SESSION_STATUS } from '../utils/statusConstants';
import type { DetailedSession } from '../types';

/**
 * Unified session detail wrapper that handles all views internally.
 * This prevents separate route navigations and duplicate API calls.
 * Tab switching updates the URL but stays within the same component instance.
 */
function SessionDetailWrapper() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  // Determine initial view from URL
  const initialView = location.pathname.includes('/technical')
    ? 'technical'
    : location.pathname.includes('/score')
    ? 'score'
    : 'conversation';
  const [currentView, setCurrentView] = useState<'conversation' | 'technical' | 'score'>(initialView);
  
  if (!sessionId) {
    return <div>Error: Session ID not found</div>;
  }

  // Handle view changes by updating URL and internal state
  const handleViewChange = (newView: 'conversation' | 'technical' | 'score') => {
    setCurrentView(newView);
    if (newView === 'technical') {
      navigate(`/sessions/${sessionId}/technical`, { replace: true });
    } else if (newView === 'score') {
      navigate(`/sessions/${sessionId}/score`, { replace: true });
    } else {
      navigate(`/sessions/${sessionId}`, { replace: true });
    }
  };

  // Timeline/content component factory based on current view
  const renderTimeline = (
    session: DetailedSession,
    autoScroll?: boolean,
    progressStatus?: string,
    agentProgressStatuses?: Map<string, string>,
    onSelectedAgentChange?: (executionId: string | null) => void
  ) => {
    // Use provided autoScroll preference, or default to enabled for live sessions
    const shouldAutoScroll = autoScroll !== undefined ? autoScroll : (session.status === SESSION_STATUS.IN_PROGRESS || session.status === SESSION_STATUS.PENDING);

    if (currentView === 'score') {
      return <ScoreDetailView session={session} />;
    } else if (currentView === 'technical') {
      return <TechnicalTimeline session={session} autoScroll={shouldAutoScroll} progressStatus={progressStatus} />;
    } else {
      return <ConversationTimeline session={session} autoScroll={shouldAutoScroll} progressStatus={progressStatus} agentProgressStatuses={agentProgressStatuses} onSelectedAgentChange={onSelectedAgentChange} />;
    }
  };

  return (
    <SessionProvider>
      <SessionDetailPageBase
        viewType={currentView}
        timelineComponent={renderTimeline}
        onViewChange={handleViewChange}
      />
    </SessionProvider>
  );
}

export default SessionDetailWrapper;
