import React from 'react';
import { Box, Skeleton, Card } from '@mui/material';
import SessionDetailPageBase from './SessionDetailPageBase';
import ConversationTimeline from './ConversationTimeline';
import type { DetailedSession } from '../types';

// Loading skeleton components
const ConversationSkeleton = () => (
  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
    {[1, 2].map((i) => (
      <Card key={i} sx={{ mb: 3 }}>
        <Box sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
          <Skeleton variant="circular" width={48} height={48} />
          <Box sx={{ flex: 1 }}>
            <Skeleton variant="text" width="40%" height={28} />
            <Skeleton variant="text" width="60%" height={20} />
          </Box>
        </Box>
        <Box sx={{ p: 2, pt: 0 }}>
          {[1, 2, 3].map((j) => (
            <Box key={j} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, mb: 2 }}>
              <Skeleton variant="text" width={28} height={28} />
              <Skeleton variant="text" width="80%" height={24} />
            </Box>
          ))}
        </Box>
      </Card>
    ))}
  </Box>
);

/**
 * Conversation-focused session detail page
 * Uses the shared SessionDetailPageBase with conversation-specific timeline rendering
 */
function ConversationSessionDetailPage() {
  // Timeline component factory for conversation view
  const renderConversationTimeline = (session: DetailedSession, useVirtualization?: boolean) => (
    <ConversationTimeline 
      session={session} 
      useVirtualization={useVirtualization} 
    />
  );

  return (
    <SessionDetailPageBase
      viewType="conversation"
      timelineComponent={renderConversationTimeline}
      timelineSkeleton={<ConversationSkeleton />}
    />
  );
}

export default ConversationSessionDetailPage;