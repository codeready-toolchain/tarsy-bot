import { lazy, Suspense } from 'react';
import { Box, Skeleton, Alert, Typography } from '@mui/material';
import type { DetailedSession } from '../types';

// Lazy load existing timeline components
const NestedAccordionTimeline = lazy(() => import('./NestedAccordionTimeline'));
const VirtualizedAccordionTimeline = lazy(() => import('./VirtualizedAccordionTimeline'));

// Performance thresholds (match those in SessionDetailPageBase)
const LARGE_SESSION_THRESHOLD = 50; // interactions

interface TechnicalTimelineProps {
  session: DetailedSession;
  useVirtualization?: boolean;
  autoScroll?: boolean;
}

// Loading skeleton for technical timeline
const TechnicalTimelineSkeleton = () => (
  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    {[1, 2, 3].map((i) => (
      <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Skeleton variant="circular" width={32} height={32} />
        <Box sx={{ flex: 1 }}>
          <Skeleton variant="text" width="70%" />
          <Skeleton variant="text" width="40%" />
        </Box>
      </Box>
    ))}
  </Box>
);

/**
 * Technical Timeline Component
 * Renders session stages in detailed technical format with interactions and communications
 * Plugs into the shared SessionDetailPageBase
 */
function TechnicalTimeline({ 
  session, 
  useVirtualization = false,
  autoScroll = true
}: TechnicalTimelineProps) {
  
  if (!session.stages || session.stages.length === 0) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        <Typography variant="h6" gutterBottom>
          Backend Chain Execution Error
        </Typography>
        <Typography variant="body2">
          This session is missing stage execution data. All sessions should be processed as chains.
        </Typography>
        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Session ID: {session.session_id}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Agent Type: {session.agent_type}
          </Typography>
        </Box>
      </Alert>
    );
  }

  // TODO: Remove fallbacks once backend consistently provides chain_id and current_stage_index
  const chainExecution = {
    chain_id: session.chain_id ?? 'unknown-chain',
    chain_definition: session.chain_definition,
    current_stage_index: session.current_stage_index ?? 0,
    current_stage_id: session.current_stage_id,
    stages: session.stages
  };

  return (
    <Suspense fallback={<TechnicalTimelineSkeleton />}>
      {useVirtualization ? (
        <VirtualizedAccordionTimeline
          chainExecution={chainExecution}
          maxVisibleInteractions={LARGE_SESSION_THRESHOLD}
          autoScroll={autoScroll}
        />
      ) : (
        <NestedAccordionTimeline
          chainExecution={chainExecution}
          autoScroll={autoScroll}
        />
      )}
    </Suspense>
  );
}

export default TechnicalTimeline;
