import React, { useEffect, useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  Alert,
  AlertTitle,
  Skeleton,
  Divider,
  Chip
} from '@mui/material';
import { Warning, InfoOutlined } from '@mui/icons-material';
import { apiClient } from '../services/api';
import MarkdownRenderer from './MarkdownRenderer';
import type { SessionScore, DetailedSession } from '../types';

interface ScoreDetailViewProps {
  session: DetailedSession;
}

const ScoreSkeleton = () => (
  <Paper sx={{ p: 3 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
      <Skeleton variant="circular" width={40} height={40} />
      <Box sx={{ flex: 1 }}>
        <Skeleton variant="text" width="40%" height={32} />
        <Skeleton variant="text" width="60%" height={20} />
      </Box>
    </Box>
    <Skeleton variant="rectangular" height={200} />
  </Paper>
);

/**
 * ScoreDetailView displays the complete score analysis for a session
 *
 * Shows:
 * - Score analysis card (breakdown + reasoning)
 * - Missing tools analysis (freeform text)
 */
const ScoreDetailView: React.FC<ScoreDetailViewProps> = ({ session }) => {
  const [score, setScore] = useState<SessionScore | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchScore = async () => {
      try {
        setLoading(true);
        setError(null);
        const scoreData = await apiClient.getSessionScore(session.session_id);
        setScore(scoreData);
      } catch (err) {
        // 404 means not scored yet - this is expected
        if (err && typeof err === 'object' && 'response' in err) {
          const axiosError = err as any;
          if (axiosError.response?.status === 404) {
            setScore(null);
            setError(null);
          } else {
            setError('Failed to load score');
          }
        } else {
          setError('Failed to load score');
        }
      } finally {
        setLoading(false);
      }
    };

    fetchScore();
  }, [session.session_id]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <ScoreSkeleton />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        <AlertTitle>Error Loading Score</AlertTitle>
        {error}
      </Alert>
    );
  }

  if (!score) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {/* Not scored message */}
        <Paper sx={{ p: 3 }}>
          <Alert severity="info">
            <AlertTitle>Session Not Scored</AlertTitle>
            This session has not been scored yet. Use the "Score Session" button to trigger an analysis.
          </Alert>
        </Paper>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Score Analysis Card */}
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 3 }}>
          Quality Score Analysis
        </Typography>

        {/* Scoring status messages */}
        {score.status === 'pending' && (
          <Alert severity="info" sx={{ mb: 2 }}>
            <AlertTitle>Scoring Pending</AlertTitle>
            Score analysis has been requested and is waiting to start.
          </Alert>
        )}

        {score.status === 'in_progress' && (
          <Alert severity="info" sx={{ mb: 2 }}>
            <AlertTitle>Scoring in Progress</AlertTitle>
            The LLM judge is analyzing the investigation methodology. This may take 30-60 seconds.
          </Alert>
        )}

        {score.status === 'failed' && (
          <Alert severity="error" sx={{ mb: 2 }}>
            <AlertTitle>Scoring Failed</AlertTitle>
            {score.error_message || 'An error occurred during scoring.'}
          </Alert>
        )}

        {/* Score analysis (only if completed) */}
        {score.status === 'completed' && score.score_analysis && (
          <Box>
            {/* Criteria version warning */}
            {!score.current_prompt_used && (
              <Alert severity="warning" icon={<Warning />} sx={{ mb: 2 }}>
                <AlertTitle>Outdated Criteria</AlertTitle>
                This score was calculated using an older version of the scoring criteria.
                Consider re-scoring to get results based on current standards.
              </Alert>
            )}

            {/* Score analysis text */}
            <MarkdownRenderer
              content={score.score_analysis}
              copyTooltip="Copy analysis"
            />

            {/* Metadata */}
            <Box sx={{ mt: 2, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <Chip
                icon={<InfoOutlined />}
                label={`Scored by: ${score.score_triggered_by}`}
                size="small"
                variant="outlined"
              />
              <Chip
                label={`Scored at: ${new Date(score.started_at_us / 1000).toLocaleString()}`}
                size="small"
                variant="outlined"
              />
              {score.completed_at_us && (
                <Chip
                  label={`Duration: ${Math.round((score.completed_at_us - score.started_at_us) / 1000000)}s`}
                  size="small"
                  variant="outlined"
                />
              )}
            </Box>
          </Box>
        )}
      </Paper>

      {/* Missing Tools Analysis Card */}
      {score.status === 'completed' && score.missing_tools_analysis && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
            Missing Tools Analysis
          </Typography>

          <Divider sx={{ mb: 2 }} />

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            The judge identified MCP tools that should have been used but weren't during the investigation.
            This analysis helps prioritize which tools to make available for future alerts.
          </Typography>

          <MarkdownRenderer
            content={score.missing_tools_analysis}
            copyTooltip="Copy missing tools analysis"
          />
        </Paper>
      )}
    </Box>
  );
};

export default ScoreDetailView;
