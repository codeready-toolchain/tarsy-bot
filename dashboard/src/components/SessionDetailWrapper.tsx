import { useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { SessionProvider } from '../contexts/SessionContext';
import SessionDetailPageBase from './SessionDetailPageBase';
import ConversationTimeline from './ConversationTimeline';
import TechnicalTimeline from './TechnicalTimeline';
import type { DetailedSession } from '../types';

/**
 * Unified session detail wrapper that handles both views internally.
 * This prevents separate route navigations and duplicate API calls.
 * Tab switching updates the URL but stays within the same component instance.
 */
function SessionDetailWrapper() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  
  // Determine initial view from URL
  const initialView = location.pathname.includes('/technical') ? 'technical' : 'conversation';
  const [currentView, setCurrentView] = useState<'conversation' | 'technical'>(initialView);
  
  if (!sessionId) {
    return <div>Error: Session ID not found</div>;
  }

  // Handle view changes by updating URL and internal state
  const handleViewChange = (newView: 'conversation' | 'technical') => {
    setCurrentView(newView);
    if (newView === 'technical') {
      navigate(`/sessions/${sessionId}/technical`, { replace: true });
    } else {
      navigate(`/sessions/${sessionId}`, { replace: true });
    }
  };

  // Timeline component factory based on current view
  const renderTimeline = (session: DetailedSession, useVirtualization?: boolean, autoScroll?: boolean) => {
    // Use provided autoScroll preference, or default to enabled for live sessions
    const shouldAutoScroll = autoScroll !== undefined ? autoScroll : (session.status === 'in_progress' || session.status === 'pending');
    
    if (currentView === 'technical') {
      return <TechnicalTimeline session={session} useVirtualization={useVirtualization} autoScroll={shouldAutoScroll} />;
    } else {
      return <ConversationTimeline session={session} useVirtualization={useVirtualization} autoScroll={shouldAutoScroll} />;
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
