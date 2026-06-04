/**
 * Executions page - View execution history and real-time status
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Alert,
  CircularProgress,
  ToggleButtonGroup,
  ToggleButton,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Tooltip,
  Collapse,
  List,
  ListItem,
  ListItemText,
  Checkbox,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  SkipNext as SkipIcon,
  Cancel as CancelIcon,
  Visibility as ViewIcon,
  KeyboardArrowDown as ExpandMoreIcon,
  KeyboardArrowUp as ExpandLessIcon,
  CheckCircle as CompletedIcon,
  Error as ErrorIcon,
  Pending as PendingIcon,
  Cancel as SkippedIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  TableChart as CsvIcon,
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useStore } from '../store';
import type { ExecutionStatusResponse, StepResult } from '../types/api';
import { getStatusChipColor } from '../constants/executionStatus';

type StatusFilter = 'all' | 'running' | 'paused' | 'completed' | 'failed';

export function Executions() {
  const setActiveExecutionId = useStore((state) => state.setActiveExecutionId);
  const setPlaybookSubTab = useStore((state) => state.setPlaybookSubTab);
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const executionUpdates = useStore((state) => state.executionUpdates);

  const toggleRowExpansion = (executionId: string) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(executionId)) {
        newSet.delete(executionId);
      } else {
        newSet.add(executionId);
      }
      return newSet;
    });
  };

  // Helper function to get step status icon
  const getStepStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CompletedIcon color="success" fontSize="small" />;
      case 'failed':
        return <ErrorIcon color="error" fontSize="small" />;
      case 'cancelled':
        return <SkippedIcon color="disabled" fontSize="small" />;
      case 'skipped':
        return <SkippedIcon color="warning" fontSize="small" />;
      default:
        return <PendingIcon color="disabled" fontSize="small" />;
    }
  };

  // Helper function to format timestamp (Australian format: DD/MM/YYYY HH:MM:SS)
  const formatTimestamp = (timestamp?: string | null): string => {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const seconds = date.getSeconds().toString().padStart(2, '0');
    return `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
  };

  // Helper function to calculate duration
  const calculateDuration = (startedAt?: string | null, completedAt?: string | null): string => {
    if (!startedAt) return '-';

    const start = new Date(startedAt).getTime();
    const end = completedAt ? new Date(completedAt).getTime() : Date.now();
    const durationMs = end - start;

    const seconds = Math.floor(durationMs / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  // Fetch executions from API
  const { data: executions = [], isLoading, error } = useQuery<ExecutionStatusResponse[]>({
    queryKey: ['executions'],
    queryFn: () => api.executions.list({ limit: 50 }),
    refetchInterval: 2000, // Refetch every 2 seconds for more responsive updates
  });

  // Apply real-time updates from WebSocket to the execution list
  const updatedExecutions = executions.map((exec) => {
    const update = executionUpdates.get(exec.execution_id);
    if (update) {
      return {
        ...exec,
        status: update.status,
        current_step_index: update.current_step_index,
        error: update.error || exec.error,
        started_at: update.started_at || exec.started_at,
        completed_at: update.completed_at || exec.completed_at,
        step_results: update.step_results || exec.step_results || [],
      };
    }
    return exec;
  });

  // Trigger refetch when executions complete via WebSocket
  useEffect(() => {
    // Check if any WebSocket updates show completed/failed status
    const shouldRefetch = Array.from(executionUpdates.values()).some(
      update => update.status === 'completed' || update.status === 'failed'
    );

    if (shouldRefetch) {
      // Debounce the refetch to avoid excessive calls
      const timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['executions'] });
      }, 1000);

      return () => clearTimeout(timer);
    }
  }, [executionUpdates, queryClient]);

  // Filter executions by status
  const filteredExecutions = statusFilter === 'all'
    ? updatedExecutions
    : updatedExecutions.filter((exec) => exec.status === statusFilter);

  // Pause execution mutation
  const pauseMutation = useMutation({
    mutationFn: (executionId: string) => api.executions.pause(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      setSnackbarMessage('Execution paused');
      setSnackbarOpen(true);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to pause: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Resume execution mutation
  const resumeMutation = useMutation({
    mutationFn: (executionId: string) => api.executions.resume(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      setSnackbarMessage('Execution resumed');
      setSnackbarOpen(true);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to resume: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Skip step mutation
  const skipMutation = useMutation({
    mutationFn: (executionId: string) => api.executions.skip(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      setSnackbarMessage('Step skipped');
      setSnackbarOpen(true);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to skip: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Cancel execution mutation
  const cancelMutation = useMutation({
    mutationFn: (executionId: string) => api.executions.cancel(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      setSnackbarMessage('Execution cancelled');
      setSnackbarOpen(true);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to cancel: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Delete execution mutation
  const deleteMutation = useMutation({
    mutationFn: async (executionIds: string[]) => {
      // Delete all selected executions in parallel
      await Promise.all(executionIds.map(id => api.executions.delete(id)));
      return executionIds.length;
    },
    onSuccess: (count) => {
      queryClient.invalidateQueries({ queryKey: ['executions'] });
      setSnackbarMessage(`${count} execution${count > 1 ? 's' : ''} deleted successfully`);
      setSnackbarOpen(true);
      setSelectedIds(new Set());
      setDeleteDialogOpen(false);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to delete: ${(error as Error).message}`);
      setSnackbarOpen(true);
      setDeleteDialogOpen(false);
    },
  });

  // Toggle individual checkbox
  const toggleSelection = (executionId: string) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(executionId)) {
        newSet.delete(executionId);
      } else {
        newSet.add(executionId);
      }
      return newSet;
    });
  };

  // Toggle select all checkbox
  const toggleSelectAll = () => {
    if (selectedIds.size === filteredExecutions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredExecutions.map((e) => e.execution_id)));
    }
  };

  // Handle delete button click
  const handleDeleteClick = () => {
    if (selectedIds.size > 0) {
      setDeleteDialogOpen(true);
    }
  };

  // Handle delete confirmation
  const handleDeleteConfirm = () => {
    deleteMutation.mutate(Array.from(selectedIds));
  };

  // Handle manual refresh
  const handleManualRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['executions'] });
    setSnackbarMessage('Executions list refreshed');
    setSnackbarOpen(true);
  };

  // Helper function to download report entries as CSV
  const handleDownloadCsv = async (execution: ExecutionStatusResponse) => {
    const response = await fetch(`/api/executions/${execution.execution_id}/report.csv`);
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `report_${execution.execution_id.slice(0, 8)}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Helper function to download execution results as JSON
  const handleDownloadResults = (execution: ExecutionStatusResponse) => {
    const dataStr = JSON.stringify(execution, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `execution_${execution.execution_id}_${execution.playbook_name.replace(/\s+/g, '_')}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Helper function to find the last step with meaningful output
  const getLastStepWithOutput = (stepResults: StepResult[] | undefined) => {
    if (!stepResults || stepResults.length === 0) return null;

    // Find the last step that has output data
    for (let i = stepResults.length - 1; i >= 0; i--) {
      const step = stepResults[i];
      if (step.output && Object.keys(step.output).length > 0) {
        return { step, index: i };
      }
    }
    return null;
  };

  return (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Typography variant="h4" gutterBottom>
        Executions
      </Typography>

      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Monitor playbook execution status in real-time
      </Typography>

      {/* Status Filter, Refresh Button, and Delete Button */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <ToggleButtonGroup
            value={statusFilter}
            exclusive
            onChange={(_, newFilter) => newFilter && setStatusFilter(newFilter)}
            aria-label="Filter executions by status"
            size="small"
          >
            <ToggleButton value="all" aria-label="Show all executions">
              All ({updatedExecutions.length})
            </ToggleButton>
            <ToggleButton value="running" aria-label="Show running executions">
              Running ({updatedExecutions.filter((e) => e.status === 'running').length})
            </ToggleButton>
            <ToggleButton value="paused" aria-label="Show paused executions">
              Paused ({updatedExecutions.filter((e) => e.status === 'paused').length})
            </ToggleButton>
            <ToggleButton value="completed" aria-label="Show completed executions">
              Completed ({updatedExecutions.filter((e) => e.status === 'completed').length})
            </ToggleButton>
            <ToggleButton value="failed" aria-label="Show failed executions">
              Failed ({updatedExecutions.filter((e) => e.status === 'failed').length})
            </ToggleButton>
          </ToggleButtonGroup>

          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={handleManualRefresh}
            size="small"
          >
            Refresh
          </Button>
        </Box>

        {selectedIds.size > 0 && (
          <Button
            variant="contained"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={handleDeleteClick}
            disabled={deleteMutation.isPending}
          >
            Delete Selected ({selectedIds.size})
          </Button>
        )}
      </Box>

      {/* Loading state */}
      {isLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <CircularProgress size={20} aria-label="Loading executions" />
          <Typography variant="body2" color="text.secondary">
            Loading executions...
          </Typography>
        </Box>
      )}

      {/* Error state */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load executions: {(error as Error).message}
        </Alert>
      )}

      {/* Empty state */}
      {!isLoading && !error && filteredExecutions.length === 0 && (
        <Alert severity="info">
          {statusFilter === 'all'
            ? 'No executions yet. Start a playbook from the Playbooks page.'
            : `No ${statusFilter} executions found.`}
        </Alert>
      )}

      {/* Execution Table */}
      {!isLoading && !error && filteredExecutions.length > 0 && (
        <TableContainer component={Paper} sx={{ width: '100%', maxWidth: '100%' }}>
          <Table size="medium" sx={{ tableLayout: 'fixed', width: '100%' }}>
            <TableHead>
              <TableRow>
                <TableCell width="5%" padding="checkbox">
                  <Checkbox
                    indeterminate={selectedIds.size > 0 && selectedIds.size < filteredExecutions.length}
                    checked={filteredExecutions.length > 0 && selectedIds.size === filteredExecutions.length}
                    onChange={toggleSelectAll}
                    inputProps={{ 'aria-label': 'Select all executions' }}
                  />
                </TableCell>
                <TableCell width="5%"></TableCell>
                <TableCell width="25%">Playbook</TableCell>
                <TableCell width="10%">Status</TableCell>
                <TableCell width="10%">Progress</TableCell>
                <TableCell width="20%">Started</TableCell>
                <TableCell width="10%">Duration</TableCell>
                <TableCell width="15%" align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredExecutions.map((execution) => {
                const isExpanded = expandedRows.has(execution.execution_id);
                return (
                  <>
                    <TableRow
                      key={execution.execution_id}
                      sx={{ '&:hover': { backgroundColor: 'action.hover' } }}
                    >
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={selectedIds.has(execution.execution_id)}
                          onChange={() => toggleSelection(execution.execution_id)}
                          inputProps={{ 'aria-label': `Select ${execution.playbook_name}` }}
                        />
                      </TableCell>
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={() => toggleRowExpansion(execution.execution_id)}
                          aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
                        >
                          {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                        </IconButton>
                      </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight="medium">
                      {execution.playbook_name}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={execution.status.toUpperCase()}
                      size="small"
                      color={getStatusChipColor(execution.status)}
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {execution.current_step_index != null
                        ? `${execution.current_step_index + 1} / ${execution.step_results?.length || 0}`
                        : '-'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {formatTimestamp(execution.started_at)}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {calculateDuration(execution.started_at, execution.completed_at)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Tooltip title="View details">
                      <IconButton
                        size="small"
                        color="primary"
                        onClick={() => {
                          setActiveExecutionId(execution.execution_id);
                          setPlaybookSubTab('active-execution');
                        }}
                        aria-label={`View ${execution.playbook_name} details`}
                      >
                        <ViewIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    {execution.status === 'running' && (
                      <Tooltip title="Pause">
                        <IconButton
                          size="small"
                          color="warning"
                          onClick={() => pauseMutation.mutate(execution.execution_id)}
                          aria-label={`Pause ${execution.playbook_name}`}
                        >
                          <PauseIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                    {execution.status === 'paused' && (
                      <>
                        <Tooltip title="Resume">
                          <IconButton
                            size="small"
                            color="success"
                            onClick={() => resumeMutation.mutate(execution.execution_id)}
                            aria-label={`Resume ${execution.playbook_name}`}
                          >
                            <PlayIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Skip">
                          <IconButton
                            size="small"
                            color="info"
                            onClick={() => skipMutation.mutate(execution.execution_id)}
                            aria-label={`Skip step in ${execution.playbook_name}`}
                          >
                            <SkipIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </>
                    )}
                    {(execution.status === 'running' || execution.status === 'paused') && (
                      <Tooltip title="Cancel">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => cancelMutation.mutate(execution.execution_id)}
                          aria-label={`Cancel ${execution.playbook_name}`}
                        >
                          <CancelIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={8}>
                    <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                      <Box sx={{ margin: 2 }}>
                        <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Typography variant="h6" component="div">
                            Step Details
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                            <Tooltip title="Download report entries as CSV">
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={() => handleDownloadCsv(execution)}
                                aria-label="Download report as CSV"
                              >
                                <CsvIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Download full execution results as JSON">
                              <IconButton
                                size="small"
                                color="primary"
                                onClick={() => handleDownloadResults(execution)}
                                aria-label="Download results"
                              >
                                <DownloadIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                              ID: {execution.execution_id}
                            </Typography>
                          </Box>
                        </Box>
                        {execution.step_results && execution.step_results.length > 0 ? (
                          <>
                            <List dense>
                              {execution.step_results.map((step, index) => (
                                <ListItem key={step.step_id || index}>
                                  <Box sx={{ mr: 2 }}>{getStepStatusIcon(step.status)}</Box>
                                  <ListItemText
                                    primary={`${index + 1}. ${step.step_name || 'Unnamed Step'}`}
                                    secondary={
                                      <>
                                        <Typography component="span" variant="body2" color="text.primary">
                                          Status: {step.status.toUpperCase()}
                                        </Typography>
                                        {step.started_at && (
                                          <>
                                            {' • '}
                                            Started: {formatTimestamp(step.started_at)}
                                          </>
                                        )}
                                        {step.completed_at && (
                                          <>
                                            {' • '}
                                            Completed: {formatTimestamp(step.completed_at)}
                                          </>
                                        )}
                                        {step.error && (
                                          <>
                                            <br />
                                            <Typography component="span" variant="body2" color="error">
                                              Error: {step.error}
                                            </Typography>
                                          </>
                                        )}
                                      </>
                                    }
                                  />
                                  <Chip
                                    label={step.status}
                                    size="small"
                                    color={getStatusChipColor(step.status)}
                                  />
                                </ListItem>
                              ))}
                            </List>
                            {(() => {
                              const lastStepWithOutput = getLastStepWithOutput(execution.step_results);
                              if (!lastStepWithOutput) return null;

                              return (
                                <Box sx={{ mt: 2 }}>
                                  <Typography variant="subtitle2" color="text.primary" sx={{ mb: 1 }}>
                                    Final Step Output:
                                  </Typography>
                                  <Paper
                                    variant="outlined"
                                    sx={{
                                      p: 2,
                                      bgcolor: 'background.default',
                                      maxHeight: '500px',
                                      overflow: 'auto'
                                    }}
                                  >
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                                      From Step {lastStepWithOutput.index + 1}: {lastStepWithOutput.step.step_name}
                                    </Typography>
                                    <pre style={{
                                      margin: 0,
                                      fontFamily: 'monospace',
                                      fontSize: '0.8rem',
                                      whiteSpace: 'pre-wrap',
                                      wordBreak: 'break-word'
                                    }}>
                                      {JSON.stringify(lastStepWithOutput.step.output, null, 2)}
                                    </pre>
                                  </Paper>
                                </Box>
                              );
                            })()}
                          </>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            No step details available
                          </Typography>
                        )}
                      </Box>
                    </Collapse>
                  </TableCell>
                </TableRow>
              </>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        aria-labelledby="delete-dialog-title"
        aria-describedby="delete-dialog-description"
      >
        <DialogTitle id="delete-dialog-title">
          Delete {selectedIds.size} Execution{selectedIds.size > 1 ? 's' : ''}?
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="delete-dialog-description">
            This will permanently delete the selected execution{selectedIds.size > 1 ? 's' : ''} and all associated
            screenshots. This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} color="primary">
            Cancel
          </Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained" autoFocus>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={4000}
        onClose={() => setSnackbarOpen(false)}
        message={snackbarMessage}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      />
    </Box>
  );
}
