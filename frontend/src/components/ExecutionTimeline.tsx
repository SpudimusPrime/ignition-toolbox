/**
 * ExecutionTimeline - Visual timeline component for step-by-step execution progress
 *
 * Features:
 * - Visual timeline with connector line
 * - Duration bars for each step
 * - Status icons and colors
 * - Expandable step details
 * - Time elapsed between steps
 */

import { useState } from 'react';
import {
  Box,
  Typography,
  Collapse,
  IconButton,
  Chip,
  Tooltip,
  Paper,
} from '@mui/material';
import {
  Pending as PendingIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Schedule as DurationIcon,
} from '@mui/icons-material';
import { getStatusTimelineColor, getStatusIcon } from '../constants/executionStatus';
import type { StepResult, NestedStepResult } from '../types/api';

interface ExecutionTimelineProps {
  steps: StepResult[];
  currentStepIndex?: number;
  compact?: boolean;
}

export function ExecutionTimeline({
  steps,
  currentStepIndex,
  compact = false,
}: ExecutionTimelineProps) {
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  const toggleStep = (stepId: string) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  const formatDuration = (startedAt?: string | null, completedAt?: string | null): string => {
    if (!startedAt) return '-';
    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : Date.now();
    const diffMs = end - start;

    if (diffMs < 1000) return `${diffMs}ms`;
    if (diffMs < 60000) return `${(diffMs / 1000).toFixed(1)}s`;
    const minutes = Math.floor(diffMs / 60000);
    const seconds = Math.floor((diffMs % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
  };

  const getTimeBetweenSteps = (prevStep: StepResult, currentStep: StepResult): string | null => {
    if (!prevStep.completed_at || !currentStep.started_at) return null;
    const prevEnd = new Date(prevStep.completed_at as string).getTime();
    const currentStart = new Date(currentStep.started_at as string).getTime();
    const gapMs = currentStart - prevEnd;

    if (gapMs < 100) return null; // Ignore very small gaps
    if (gapMs < 1000) return `+${gapMs}ms`;
    return `+${(gapMs / 1000).toFixed(1)}s`;
  };

  // Calculate max duration for scaling progress bars
  const maxDuration = steps.reduce((max, step) => {
    if (!step.started_at) return max;
    const start = new Date(step.started_at).getTime();
    const end = step.completed_at ? new Date(step.completed_at).getTime() : Date.now();
    return Math.max(max, end - start);
  }, 1000); // Minimum 1 second for scaling

  return (
    <Box sx={{ position: 'relative' }}>
      {/* Timeline connector line */}
      <Box
        sx={{
          position: 'absolute',
          left: compact ? 11 : 15,
          top: 20,
          bottom: 20,
          width: 2,
          bgcolor: 'divider',
          zIndex: 0,
        }}
      />

      {steps.map((step, index) => {
        const isExpanded = expandedSteps.has(step.step_id);
        const isCurrent = index === currentStepIndex;
        const hasNestedSteps = step.nested_steps && step.nested_steps.length > 0;
        const isRunningWithNested = step.status === 'running' && hasNestedSteps;
        const hasDetails = step.error || hasNestedSteps || (step.output && Object.keys(step.output).length > 0);
        const timeBetween = index > 0 ? getTimeBetweenSteps(steps[index - 1], step) : null;

        // Calculate duration bar width
        const stepDuration = step.started_at
          ? (step.completed_at
              ? new Date(step.completed_at).getTime() - new Date(step.started_at).getTime()
              : Date.now() - new Date(step.started_at).getTime())
          : 0;
        const durationPercent = Math.min(100, (stepDuration / maxDuration) * 100);

        return (
          <Box key={step.step_id || index}>
            {/* Time gap indicator */}
            {timeBetween && (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  ml: compact ? 3 : 4,
                  my: 0.5,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    color: 'text.disabled',
                    fontFamily: 'monospace',
                    fontSize: '0.65rem',
                  }}
                >
                  {timeBetween}
                </Typography>
              </Box>
            )}

            {/* Step item */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: compact ? 1 : 1.5,
                py: compact ? 0.5 : 1,
                px: compact ? 0.5 : 1,
                borderRadius: 1,
                bgcolor: isCurrent ? 'action.selected' : 'transparent',
                transition: 'background-color 0.2s',
                '&:hover': {
                  bgcolor: isCurrent ? 'action.selected' : 'action.hover',
                },
              }}
            >
              {/* Status icon with timeline dot */}
              <Box
                sx={{
                  position: 'relative',
                  zIndex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: compact ? 24 : 32,
                  height: compact ? 24 : 32,
                  borderRadius: '50%',
                  bgcolor: 'background.paper',
                  border: `2px solid ${getStatusTimelineColor(step.status)}`,
                  flexShrink: 0,
                }}
              >
                {getStatusIcon(step.status, { size: compact ? 'small' : 'medium' })}
              </Box>

              {/* Step content */}
              <Box sx={{ flex: 1, minWidth: 0 }}>
                {/* Step header */}
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    cursor: hasDetails ? 'pointer' : 'default',
                  }}
                  onClick={() => hasDetails && toggleStep(step.step_id)}
                >
                  <Typography
                    variant={compact ? 'body2' : 'subtitle2'}
                    sx={{
                      flex: 1,
                      fontWeight: isCurrent ? 600 : 400,
                      fontSize: compact ? '0.8rem' : '0.875rem',
                    }}
                    noWrap
                  >
                    {step.step_name || `Step ${index + 1}`}
                  </Typography>

                  {/* Duration chip */}
                  {step.started_at && (
                    <Tooltip title="Step duration">
                      <Chip
                        icon={<DurationIcon sx={{ fontSize: '0.75rem !important' }} />}
                        label={formatDuration(step.started_at, step.completed_at)}
                        size="small"
                        sx={{
                          height: compact ? 18 : 22,
                          fontSize: compact ? '0.65rem' : '0.7rem',
                          '& .MuiChip-icon': { ml: 0.5 },
                          '& .MuiChip-label': { px: 0.75 },
                        }}
                      />
                    </Tooltip>
                  )}

                  {/* Expand button */}
                  {hasDetails && (
                    <IconButton
                      size="small"
                      sx={{ p: 0.25 }}
                    >
                      {isExpanded ? (
                        <ExpandLessIcon sx={{ fontSize: '1rem' }} />
                      ) : (
                        <ExpandMoreIcon sx={{ fontSize: '1rem' }} />
                      )}
                    </IconButton>
                  )}
                </Box>

                {/* Duration progress bar */}
                {step.started_at && !compact && (
                  <Box sx={{ mt: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box
                      sx={{
                        flex: 1,
                        height: 4,
                        bgcolor: 'action.disabledBackground',
                        borderRadius: 2,
                        overflow: 'hidden',
                      }}
                    >
                      <Box
                        sx={{
                          width: `${durationPercent}%`,
                          height: '100%',
                          bgcolor: getStatusTimelineColor(step.status),
                          borderRadius: 2,
                          transition: 'width 0.3s ease-out',
                        }}
                      />
                    </Box>
                  </Box>
                )}

                {/* Timestamp */}
                {step.completed_at && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontSize: compact ? '0.65rem' : '0.7rem', display: 'block', mt: 0.25 }}
                  >
                    Completed at {new Date(step.completed_at).toLocaleTimeString()}
                  </Typography>
                )}

                {/* Nested steps: auto-visible while running, collapsible after */}
                <Collapse in={isRunningWithNested || isExpanded}>
                  <Box sx={{ mt: 1 }}>
                    {hasNestedSteps && (
                      <NestedStepList steps={step.nested_steps!} formatDuration={formatDuration} />
                    )}

                    {/* Error message (shown when expanded, no nested steps) */}
                    {!hasNestedSteps && step.error && (
                      <Paper
                        elevation={0}
                        sx={{
                          p: 1,
                          mb: 1,
                          bgcolor: 'error.dark',
                          borderRadius: 1,
                          border: '1px solid',
                          borderColor: 'error.main',
                        }}
                      >
                        <Typography
                          variant="caption"
                          sx={{
                            fontFamily: 'monospace',
                            color: 'error.contrastText',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                          }}
                        >
                          {step.error}
                        </Typography>
                      </Paper>
                    )}

                    {/* Step output (shown when expanded, no nested steps) */}
                    {!hasNestedSteps && step.output && Object.keys(step.output).length > 0 && (
                      <Paper
                        elevation={0}
                        sx={{
                          p: 1,
                          bgcolor: 'rgba(0, 255, 0, 0.05)',
                          borderRadius: 1,
                          border: '1px solid rgba(0, 255, 0, 0.2)',
                        }}
                      >
                        {step.output._output ? (
                          <Typography
                            variant="caption"
                            component="pre"
                            sx={{
                              fontFamily: 'monospace',
                              fontSize: '0.7rem',
                              color: '#00ff00',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              m: 0,
                            }}
                          >
                            {step.output._output}
                          </Typography>
                        ) : (
                          <Typography
                            variant="caption"
                            component="pre"
                            sx={{
                              fontFamily: 'monospace',
                              fontSize: '0.7rem',
                              color: 'text.secondary',
                              whiteSpace: 'pre-wrap',
                              m: 0,
                            }}
                          >
                            {JSON.stringify(step.output, null, 2)}
                          </Typography>
                        )}
                      </Paper>
                    )}
                  </Box>
                </Collapse>
              </Box>
            </Box>
          </Box>
        );
      })}

      {/* Empty state */}
      {steps.length === 0 && (
        <Box
          sx={{
            py: 4,
            textAlign: 'center',
          }}
        >
          <PendingIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
          <Typography variant="body2" color="text.secondary">
            No steps executed yet
          </Typography>
        </Box>
      )}
    </Box>
  );
}

function NestedStepList({
  steps,
  formatDuration,
  depth = 0,
}: {
  steps: NestedStepResult[];
  formatDuration: (start?: string | null, end?: string | null) => string;
  depth?: number;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (id: string) => setExpanded(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  return (
    <Box
      sx={{
        ml: depth === 0 ? 1 : 0,
        pl: 1.5,
        borderLeft: '2px solid',
        borderLeftColor: depth === 0 ? 'divider' : 'action.disabledBackground',
        display: 'flex',
        flexDirection: 'column',
        gap: 0.25,
      }}
    >
      {steps.map((step, index) => {
        const color = getStatusTimelineColor(step.status);
        const hasChildren = step.nested_steps && step.nested_steps.length > 0;
        const isRunning = step.status === 'running';
        const isOpen = isRunning || expanded.has(step.step_id || String(index));
        return (
          <Box key={step.step_id || index}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                py: 0.5,
                px: 0.75,
                borderRadius: 1,
                cursor: hasChildren ? 'pointer' : 'default',
                '&:hover': { bgcolor: 'action.hover' },
              }}
              onClick={() => hasChildren && toggle(step.step_id || String(index))}
            >
              <Box
                sx={{
                  width: 20,
                  height: 20,
                  borderRadius: '50%',
                  border: `2px solid ${color}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  bgcolor: 'background.paper',
                }}
              >
                {getStatusIcon(step.status, { size: 'small' })}
              </Box>
              <Typography
                variant="caption"
                sx={{
                  flex: 1,
                  fontSize: depth === 0 ? '0.75rem' : '0.7rem',
                  color: isRunning ? 'text.primary' : 'text.secondary',
                  fontWeight: isRunning ? 500 : 400,
                }}
                noWrap
              >
                {step.step_name || step.step_id}
              </Typography>
              {step.started_at && (
                <Typography
                  variant="caption"
                  sx={{ fontSize: '0.65rem', color: 'text.disabled', fontFamily: 'monospace', flexShrink: 0 }}
                >
                  {formatDuration(step.started_at, step.completed_at)}
                </Typography>
              )}
              {step.error && (
                <Tooltip title={step.error}>
                  <Typography variant="caption" sx={{ fontSize: '0.65rem', color: 'error.main', flexShrink: 0 }}>
                    ✕
                  </Typography>
                </Tooltip>
              )}
              {hasChildren && (
                <Typography variant="caption" sx={{ fontSize: '0.65rem', color: 'text.disabled', flexShrink: 0 }}>
                  {isOpen ? '▾' : '▸'}
                </Typography>
              )}
            </Box>
            {hasChildren && (
              <Collapse in={isOpen}>
                <NestedStepList
                  steps={step.nested_steps!}
                  formatDuration={formatDuration}
                  depth={depth + 1}
                />
              </Collapse>
            )}
          </Box>
        );
      })}
    </Box>
  );
}
