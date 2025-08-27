import { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { 
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Breadcrumbs,
  Link,
  IconButton
} from '@mui/material';
import { NavigateBefore, NavigateNext } from '@mui/icons-material';
import { parseSessionConversation, getConversationStats } from '../utils/conversationParser';
import type { ParsedSession } from '../utils/conversationParser';
import type { DetailedSession } from '../types';
import StageConversationCard from './StageConversationCard';
import CopyButton from './CopyButton';

interface ConversationTimelineProps {
  session: DetailedSession;
  useVirtualization?: boolean;
  autoScroll?: boolean;
}

/**
 * Conversation Timeline Component
 * Renders session stages in conversation format with clean AI reasoning flow
 * Plugs into the shared SessionDetailPageBase
 */
function ConversationTimeline({ 
  session, 
  useVirtualization: _useVirtualization, // Not used for conversation view currently
  autoScroll = true
}: ConversationTimelineProps) {
  const [parsedSession, setParsedSession] = useState<ParsedSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(0);
  const [recentlyUpdatedStages, setRecentlyUpdatedStages] = useState<Set<string>>(new Set());
  
  // Auto-scroll functionality
  const stagesContainerRef = useRef<HTMLDivElement>(null);
  const previousStepCountsRef = useRef<Map<string, number>>(new Map());
  const userScrolledAwayRef = useRef<boolean>(false);
  const isUserAtBottomRef = useRef<boolean>(true);

  // Memoize conversation stats to prevent recalculation on every render - MOVED BEFORE EARLY RETURNS
  const conversationStats = useMemo(() => {
    return parsedSession ? getConversationStats(parsedSession) : {
      totalSteps: 0,
      thoughtsCount: 0,
      actionsCount: 0,
      successfulActions: 0,
      analysisCount: 0,
      errorsCount: 0
    };
  }, [parsedSession]);
  
  // Memoize formatSessionForCopy to prevent recalculation on every render - MOVED BEFORE EARLY RETURNS
  const formatSessionForCopy = useMemo((): string => {
    if (!parsedSession) return '';
    
    let content = `=== CONVERSATION SESSION ===\n`;
    content += `Session ID: ${parsedSession.session_id}\n`;
    content += `Status: ${parsedSession.status}\n`;
    content += `Stages: ${parsedSession.stages.length}\n`;
    content += `Total Steps: ${conversationStats.totalSteps}\n`;
    content += `${'='.repeat(60)}\n\n`;
    
    parsedSession.stages.forEach((stage, stageIndex) => {
      content += `=== Stage ${stageIndex + 1}: ${stage.stage_name} ===\n`;
      content += `Agent: ${stage.agent}\n`;
      content += `Status: ${stage.status}\n`;
      content += `${'='.repeat(60)}\n\n`;
      
      stage.steps.forEach((step, stepIndex) => {
        const emoji = step.type === 'thought' ? '💭' : 
                     step.type === 'action' ? '🔧' : 
                     step.type === 'analysis' ? '🎯' : '❌';
        
        content += `${emoji} ${step.content}\n`;
        
        if (step.type === 'action' && step.actionName) {
          content += `   Action: ${step.actionName}${step.actionInput ? ` ${step.actionInput}` : ''}\n`;
          
          if (step.actionResult) {
            const result = typeof step.actionResult === 'string' ? 
                          step.actionResult : 
                          JSON.stringify(step.actionResult, null, 2);
            content += `   Result: ${result}\n`;
          }
        }
        
        if (stepIndex < stage.steps.length - 1) {
          content += '\n';
        }
      });
      
      content += '\n\n';
    });
    
    if (parsedSession.finalAnalysis) {
      content += `=== FINAL ANALYSIS ===\n`;
      content += `${parsedSession.finalAnalysis}\n`;
    }
    
    return content;
  }, [parsedSession, conversationStats.totalSteps]);

  // Helper function to check if user is at bottom of scrollable area
  const isAtBottom = useCallback((): boolean => {
    // Check if user is at bottom of page
    const documentHeight = document.documentElement.scrollHeight;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const windowHeight = window.innerHeight;

    // Consider user at bottom if within 50px of the bottom
    const threshold = 50;
    return documentHeight - scrollTop - windowHeight <= threshold;
  }, []);

  // Scroll position-based auto-scroll control
  useEffect(() => {
    if (!autoScroll) return;

    // Initialize scroll position on mount
    isUserAtBottomRef.current = isAtBottom();
    userScrolledAwayRef.current = !isUserAtBottomRef.current;

    if (process.env.NODE_ENV !== 'production') {
      console.log(`🚀 Conversation: Initializing scroll detection: isAtBottom=${isUserAtBottomRef.current}, userScrolledAway=${userScrolledAwayRef.current}`);
    }

    const handleScroll = () => {
      const wasAtBottom = isUserAtBottomRef.current;
      const isNowAtBottom = isAtBottom();

      if (process.env.NODE_ENV !== 'production') {
        console.log(`📜 Conversation Scroll event: wasAtBottom=${wasAtBottom}, isNowAtBottom=${isNowAtBottom}, userScrolledAway=${userScrolledAwayRef.current}`);
      }

      // Update our tracking of user's position
      isUserAtBottomRef.current = isNowAtBottom;

      if (wasAtBottom && !isNowAtBottom) {
        // User scrolled away from bottom - disable auto-scroll
        userScrolledAwayRef.current = true;
        if (process.env.NODE_ENV !== 'production') {
          console.log(`👆 Conversation: User scrolled away from bottom - disabling auto-scroll`);
        }
      } else if (!wasAtBottom && isNowAtBottom) {
        // User scrolled back to bottom - re-enable auto-scroll
        userScrolledAwayRef.current = false;
        if (process.env.NODE_ENV !== 'production') {
          console.log(`👇 Conversation: User scrolled back to bottom - re-enabling auto-scroll`);
        }
      }
    };

    // Listen to scroll events on window
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, [autoScroll, isAtBottom]);

  // Memoize stage status calculations - MOVED BEFORE EARLY RETURNS
  const stageStatusCounts = useMemo(() => {
    if (!parsedSession) return { completed: 0, failed: 0 };
    return {
      completed: parsedSession.stages.filter(s => s.status === 'completed').length,
      failed: parsedSession.stages.filter(s => s.status === 'failed').length
    };
  }, [parsedSession]);

  // Parse session data into conversation format with smart updates
  useEffect(() => {
    if (session) {
      try {
        const parsed = parseSessionConversation(session);
        
        // Check if this is a meaningful update to avoid unnecessary re-renders
        setParsedSession(prevParsed => {
          // If no previous data, always update
          if (!prevParsed) {
            console.log('🔄 Initial conversation parsing');
            return parsed;
          }
          
          // Check if meaningful data has changed
          const stagesChanged = prevParsed.stages.length !== parsed.stages.length;
          const statusChanged = prevParsed.status !== parsed.status;
          const analysisChanged = prevParsed.finalAnalysis !== parsed.finalAnalysis;
          
          // Check if any stage content has changed (more thorough check)
          const stageContentChanged = parsed.stages.some((newStage, index) => {
            const prevStage = prevParsed.stages[index];
            if (!prevStage) return true;
            
            return prevStage.steps.length !== newStage.steps.length ||
                   prevStage.status !== newStage.status ||
                   prevStage.errorMessage !== newStage.errorMessage;
          });
          
          if (stagesChanged || statusChanged || analysisChanged || stageContentChanged) {
            console.log('🔄 Meaningful conversation data changed, updating:', {
              stagesChanged,
              statusChanged,
              analysisChanged,
              stageContentChanged
            });
            
            // Track which stages have been updated
            const updatedStageIds = new Set<string>();
            parsed.stages.forEach((newStage, index) => {
              const prevStage = prevParsed.stages[index];
              if (!prevStage || 
                  prevStage.steps.length !== newStage.steps.length ||
                  prevStage.status !== newStage.status) {
                updatedStageIds.add(newStage.execution_id);
              }
            });
            
            if (updatedStageIds.size > 0) {
              setRecentlyUpdatedStages(updatedStageIds);
              
              // Clear the updated indicators after 4 seconds
              setTimeout(() => {
                setRecentlyUpdatedStages(new Set());
              }, 4000);
              
              // Auto-scroll to bottom if new steps were added
              if (autoScroll) {
                // Check if new steps were added to any stage
                let hasNewSteps = false;
                parsed.stages.forEach(stage => {
                  const currentStepCount = stage.steps.length;
                  const previousStepCount = previousStepCountsRef.current.get(stage.execution_id) || 0;
                  
                  if (currentStepCount > previousStepCount) {
                    hasNewSteps = true;
                    console.log(`🆕 New steps detected in stage ${stage.stage_name}: ${previousStepCount} → ${currentStepCount}`);
                  }
                  
                  previousStepCountsRef.current.set(stage.execution_id, currentStepCount);
                });
                
                if (hasNewSteps && stagesContainerRef.current) {
                  // Check if this update includes final analysis - prioritize this over scroll position
                  const hasAnalysisNow = parsed.finalAnalysis && parsed.finalAnalysis.length > 50;
                  
                  if (hasAnalysisNow) {
                    // For final analysis, use more lenient distance check
                    const documentHeight = document.documentElement.scrollHeight;
                    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                    const windowHeight = window.innerHeight;
                    const distanceFromBottom = documentHeight - scrollTop - windowHeight;
                    const isNearBottom = distanceFromBottom <= 200;

                    if (process.env.NODE_ENV !== 'production') {
                      console.log(`🎯 Final analysis detected: distanceFromBottom=${distanceFromBottom}, isNearBottom=${isNearBottom}, userScrolledAway=${userScrolledAwayRef.current}`);
                    }
                    
                    if (isNearBottom) {
                      setTimeout(() => {
                        const finalAnalysisElement = document.querySelector('[data-final-analysis]') as HTMLElement;
                        if (finalAnalysisElement) {
                          finalAnalysisElement.scrollIntoView({
                            behavior: 'smooth',
                            block: 'start'
                          });
                          console.log('🎯 Auto-scrolled to final analysis from conversation');
                          return;
                        } else {
                          console.log('🎯 Final analysis element not found');
                        }
                      }, 200);
                    } else {
                      console.log('🎯 Final analysis auto-scroll skipped - user scrolled too far up');
                    }
                  } else if (!userScrolledAwayRef.current) {
                    // Regular conversation steps - respect userScrolledAwayRef
                    if (process.env.NODE_ENV !== 'production') {
                      console.log(`🔄 Conversation auto-scroll check: userScrolledAway=${userScrolledAwayRef.current}, isAtBottom=${isAtBottom()}`);
                    }

                    setTimeout(() => {
                      // Double-check that user hasn't scrolled away during the delay
                      if (userScrolledAwayRef.current) {
                        if (process.env.NODE_ENV !== 'production') {
                          console.log('🔄 Conversation auto-scroll cancelled - user scrolled away during delay');
                        }
                        return;
                      }

                      // Scroll to the last stage card
                      const lastStageElement = stagesContainerRef.current?.lastElementChild as HTMLElement;
                      if (lastStageElement) {
                        lastStageElement.scrollIntoView({
                          behavior: 'smooth',
                          block: 'end'
                        });
                        console.log('🔄 Auto-scrolled to last conversation step');
                      }
                    }, 200);
                  } else {
                    if (process.env.NODE_ENV !== 'production') {
                      console.log('🔄 Conversation auto-scroll skipped - user has scrolled away');
                    }
                  }
                }
              }
            }
            
            return parsed;
          } else {
            console.log('🔄 No meaningful conversation changes, keeping existing data');
            return prevParsed;
          }
        });
        
        setError(null);
      } catch (err) {
        console.error('Failed to parse session conversation:', err);
        setError('Failed to parse conversation data');
        setParsedSession(null);
      }
    }
  }, [session]);

  const navigateToStage = (direction: 'next' | 'prev') => {
    if (!parsedSession) return;
    
    const newIndex = direction === 'next' 
      ? Math.min(currentStageIndex + 1, parsedSession.stages.length - 1)
      : Math.max(currentStageIndex - 1, 0);
    
    setCurrentStageIndex(newIndex);
  };

  if (error) {
    return (
      <Card>
        <CardContent sx={{ p: 3 }}>
          <Typography color="error" variant="h6">
            Conversation Parsing Error
          </Typography>
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (!parsedSession) {
    return (
      <Card>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="body2" color="text.secondary">
            Loading conversation data...
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      {/* Chain Progress Header - Matching Debug View Style */}
      <CardContent sx={{ bgcolor: 'grey.50', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" color="primary.main">
            Chain: {session.chain_id || 'Unknown'}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            <CopyButton
              text={formatSessionForCopy}
              variant="button"
              buttonVariant="outlined"
              size="small"
              label="Copy Entire Flow"
              tooltip="Copy all stages and conversations to clipboard"
            />
            <IconButton 
              size="small" 
              onClick={() => navigateToStage('prev')}
              disabled={currentStageIndex === 0}
            >
              <NavigateBefore />
            </IconButton>
            <Chip 
              label={`Stage ${currentStageIndex + 1} of ${parsedSession.stages.length}`}
              color="primary"
              variant="outlined"
            />
            <IconButton 
              size="small" 
              onClick={() => navigateToStage('next')}
              disabled={currentStageIndex === parsedSession.stages.length - 1}
            >
              <NavigateNext />
            </IconButton>
          </Box>
        </Box>

        {/* Stage Navigation Breadcrumbs */}
        <Breadcrumbs separator="•" sx={{ mb: 2 }}>
          {parsedSession.stages.map((stage, index) => (
            <Link
              key={stage.execution_id}
              component="button"
              variant="body2"
              onClick={() => setCurrentStageIndex(index)}
              sx={{
                color: index === currentStageIndex ? 'primary.main' : 'text.secondary',
                fontWeight: index === currentStageIndex ? 600 : 400,
                textDecoration: 'none',
                cursor: 'pointer',
                '&:hover': { textDecoration: 'underline' }
              }}
            >
              {stage.stage_name}
            </Link>
          ))}
        </Breadcrumbs>

        {/* Overall Progress */}
        <Box display="flex" gap={2} alignItems="center" mb={2}>
          <LinearProgress 
            variant="determinate" 
            value={parsedSession.stages.length > 0 ? (stageStatusCounts.completed / parsedSession.stages.length) * 100 : 0}
            sx={{ height: 6, borderRadius: 3, flex: 1 }}
          />
          <Typography variant="body2" color="text.secondary">
            {stageStatusCounts.completed} / {parsedSession.stages.length} completed
          </Typography>
        </Box>

        {/* Chain Status Chips - Matching Debug View */}
        <Box display="flex" gap={1} flexWrap="wrap">
          <Chip 
            label={`${parsedSession.stages.length} stages`} 
            color="primary" 
            variant="outlined" 
            size="small"
          />
          <Chip 
            label={`${stageStatusCounts.completed} completed`} 
            color="success" 
            variant="outlined" 
            size="small"
          />
          {stageStatusCounts.failed > 0 && (
            <Chip 
              label={`${stageStatusCounts.failed} failed`} 
              color="error" 
              variant="outlined" 
              size="small"
            />
          )}
          <Chip 
            label={`${conversationStats.thoughtsCount} thoughts`}
            size="small"
            variant="outlined"
          />
          <Chip 
            label={`${conversationStats.successfulActions}/${conversationStats.actionsCount} actions`}
            size="small"
            variant="outlined"
            color={conversationStats.successfulActions === conversationStats.actionsCount ? 'success' : 'warning'}
          />
          <Chip 
            label={`${conversationStats.analysisCount} analyses`}
            size="small"
            variant="outlined"
            color="success"
          />
          {conversationStats.errorsCount > 0 && (
            <Chip 
              label={`${conversationStats.errorsCount} errors`}
              size="small"
              variant="outlined"
              color="error"
            />
          )}
        </Box>
      </CardContent>

      {/* Stage Conversation Cards */}
      <Box 
        ref={stagesContainerRef}
        sx={{ p: 3 }}
      >
        {parsedSession.stages.map((stage, stageIndex) => (
          <StageConversationCard
            key={`${stage.execution_id}-${stage.status}-${stage.steps.length}`}
            stage={stage}
            stageIndex={stageIndex}
            isRecentlyUpdated={recentlyUpdatedStages.has(stage.execution_id)}
          />
        ))}



        {/* Empty state for no stages */}
        {parsedSession.stages.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body2" color="text.secondary">
              No conversation steps available for this session
            </Typography>
          </Box>
        )}
      </Box>
    </Card>
  );
}

export default ConversationTimeline;
