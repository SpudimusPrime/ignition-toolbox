/**
 * PlaybookCard - Compact playbook card with expandable details
 */

import { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
  Chip,
  Box,
  Divider,
  List,
  ListItem,
  ListItemText,
  Tooltip,
  IconButton,
  Menu,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar,
  Switch,
  FormControlLabel,
  TextField,
  Collapse,
} from '@mui/material';
import {
  Settings as ConfigureIcon,
  PlayArrow as PlayIcon,
  Download as DownloadIcon,
  MoreVert as MoreVertIcon,
  List as ViewStepsIcon,
  Verified as VerifiedIcon,
  ToggleOn as EnableIcon,
  ToggleOff as DisableIcon,
  Info as InfoIcon,
  Close as ClearIcon,
  BugReport as DebugIcon,
  Edit as EditIcon,
  Check as SaveIcon,
  Cancel as CancelIcon,
  Delete as DeleteIcon,
  Schedule as ScheduleIcon,
  ContentCopy as DuplicateIcon,
  CheckCircle as CheckCircleIcon,
  RadioButtonUnchecked as NotConfiguredIcon,
  Code as CodeIcon,
  ExpandMore as ExpandMoreIcon,
  SystemUpdate as UpdateIcon,
  Store as StoreIcon,
  DriveFileMove as MoveIcon,
  GitHub as GitHubIcon,
} from '@mui/icons-material';
import type { PlaybookInfo } from '../types/api';
import { useStore } from '../store';
import { api } from '../api/client';
import { TIMING } from '../config/timing';
import { STORAGE_KEYS } from '../utils/localStorage';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import ScheduleDialog from './ScheduleDialog';

interface PlaybookCardProps {
  playbook: PlaybookInfo;
  onConfigure: (playbook: PlaybookInfo) => void;
  onExecute?: (playbook: PlaybookInfo) => void;
  onExport?: (playbook: PlaybookInfo) => void;
  onViewSteps?: (playbook: PlaybookInfo) => void;
  onEditPlaybook?: (playbook: PlaybookInfo) => void;
  onSubmitToLibrary?: (playbook: PlaybookInfo) => void;
  onPushToPrivateRepo?: (playbook: PlaybookInfo) => void;
  availableUpdate?: { latest_version: string; is_major_update: boolean; release_notes: string | null };
  sections?: Array<{ id: string; name: string }>;
  onMoveToSection?: (playbookPath: string, sectionId: string | null) => void;
}

// Get saved config for preview
interface SavedConfig {
  parameters: Record<string, string>;
  savedAt: string;
}

function getSavedConfigPreview(playbookPath: string): SavedConfig | null {
  const stored = localStorage.getItem(STORAGE_KEYS.PLAYBOOK_CONFIG(playbookPath));
  if (!stored) return null;
  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
}

export function PlaybookCard({ playbook, onConfigure, onExecute, onExport, onViewSteps, onEditPlaybook, onSubmitToLibrary, onPushToPrivateRepo, availableUpdate, sections, onMoveToSection }: PlaybookCardProps) {
  const queryClient = useQueryClient();
  const [savedConfig, setSavedConfig] = useState<SavedConfig | null>(getSavedConfigPreview(playbook.path));
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [debugMode, setDebugMode] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.PLAYBOOK_DEBUG(playbook.path));
    return stored === 'true';
  });
  const [scheduleMode, setScheduleMode] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEYS.PLAYBOOK_SCHEDULE_MODE(playbook.path));
    return stored === 'true';
  });
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editedName, setEditedName] = useState(playbook.name);
  const [editedDescription, setEditedDescription] = useState(playbook.description);
  const [duplicateDialogOpen, setDuplicateDialogOpen] = useState(false);
  const [duplicateName, setDuplicateName] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [sectionMenuAnchor, setSectionMenuAnchor] = useState<null | HTMLElement>(null);
  const selectedCredential = useStore((state) => state.selectedCredential);

  // Mutation for updating playbook to latest version
  const updatePlaybookMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`${api.getBaseUrl()}/api/playbooks/${encodeURIComponent(playbook.path)}/update`, { method: 'POST' });
      if (!response.ok) throw new Error('Update failed');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      queryClient.invalidateQueries({ queryKey: ['playbook-updates'] });
      setSnackbarMessage('Playbook updated successfully');
      setSnackbarOpen(true);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to update: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  const isDisabled = !playbook.enabled;

  // Check if required parameters are configured
  const areParamsConfigured = (): boolean => {
    if (!playbook.parameters || playbook.parameters.length === 0) {
      return true;
    }

    const hasGlobalCredential = !!selectedCredential;
    const credentialCoveredParams = ['gateway_url', 'username', 'password', 'user', 'pass', 'credential_name'];

    const requiredUserParams = playbook.parameters.filter(
      p => p.required &&
           p.default === null &&
           !credentialCoveredParams.some(cp => p.name.toLowerCase().includes(cp.toLowerCase()))
    );

    if (hasGlobalCredential) {
      if (requiredUserParams.length === 0) {
        return true;
      }

      if (savedConfig) {
        const configuredParams = Object.keys(savedConfig.parameters);
        const allRequiredConfigured = requiredUserParams.every(
          p => configuredParams.includes(p.name) && savedConfig.parameters[p.name] !== ''
        );
        if (allRequiredConfigured) {
          return true;
        }
      }
    }

    return false;
  };

  const paramsConfigured = areParamsConfigured();

  // Check for saved config updates periodically
  useEffect(() => {
    const interval = setInterval(() => {
      setSavedConfig(getSavedConfigPreview(playbook.path));
    }, TIMING.POLLING.PLAYBOOK_CONFIG_CHECK);
    return () => clearInterval(interval);
  }, [playbook.path]);

  // Mutation for verifying playbook
  const verifyMutation = useMutation({
    mutationFn: () => api.playbooks.verify(playbook.path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage('Playbook marked as verified');
      setSnackbarOpen(true);
      setMenuAnchor(null);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to verify: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Mutation for unverifying playbook
  const unverifyMutation = useMutation({
    mutationFn: () => api.playbooks.unverify(playbook.path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage('Playbook verification removed');
      setSnackbarOpen(true);
      setMenuAnchor(null);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to unverify: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Mutation for enabling playbook
  const enableMutation = useMutation({
    mutationFn: () => api.playbooks.enable(playbook.path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage('Playbook enabled');
      setSnackbarOpen(true);
      setMenuAnchor(null);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to enable: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Mutation for disabling playbook
  const disableMutation = useMutation({
    mutationFn: () => api.playbooks.disable(playbook.path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage('Playbook disabled');
      setSnackbarOpen(true);
      setMenuAnchor(null);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to disable: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Mutation for updating playbook metadata
  const updateMetadataMutation = useMutation({
    mutationFn: ({ name, description }: { name?: string; description?: string }) =>
      api.playbooks.updateMetadata(playbook.path, name, description),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage('Playbook updated successfully');
      setSnackbarOpen(true);
      setEditDialogOpen(false);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to update: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Mutation for deleting playbook
  const deleteMutation = useMutation({
    mutationFn: () => api.playbooks.delete(playbook.path),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage('Playbook deleted successfully');
      setSnackbarOpen(true);
      setMenuAnchor(null);
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to delete: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  // Mutation for duplicating playbook
  const duplicateMutation = useMutation({
    mutationFn: (newName?: string) => api.playbooks.duplicate(playbook.path, newName),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setSnackbarMessage(`Playbook duplicated: ${data.new_path}`);
      setSnackbarOpen(true);
      setMenuAnchor(null);
      setDuplicateDialogOpen(false);
      setDuplicateName('');
    },
    onError: (error) => {
      setSnackbarMessage(`Failed to duplicate: ${(error as Error).message}`);
      setSnackbarOpen(true);
    },
  });

  const handleOpenDuplicateDialog = () => {
    setDuplicateName('');
    setDuplicateDialogOpen(true);
    setMenuAnchor(null);
  };

  const handleDuplicate = () => {
    duplicateMutation.mutate(duplicateName || undefined);
  };

  const handleOpenEditDialog = () => {
    setEditedName(playbook.name);
    setEditedDescription(playbook.description);
    setEditDialogOpen(true);
    setMenuAnchor(null);
  };

  const handleSaveEdit = () => {
    updateMetadataMutation.mutate({
      name: editedName !== playbook.name ? editedName : undefined,
      description: editedDescription !== playbook.description ? editedDescription : undefined,
    });
  };

  const handleDebugModeToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newDebugMode = event.target.checked;
    setDebugMode(newDebugMode);
    localStorage.setItem(STORAGE_KEYS.PLAYBOOK_DEBUG(playbook.path), newDebugMode.toString());
  };

  const handleScheduleModeToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newScheduleMode = event.target.checked;
    setScheduleMode(newScheduleMode);
    localStorage.setItem(STORAGE_KEYS.PLAYBOOK_SCHEDULE_MODE(playbook.path), newScheduleMode.toString());
  };

  const handleExecuteClick = () => {
    if (onExecute) {
      onExecute(playbook);
    } else {
      onConfigure(playbook);
    }
  };

  const versionText = `v${playbook.version}`;

  return (
    <Card
      elevation={3}
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        opacity: isDisabled ? 0.7 : 1,
        border: '2px solid',
        borderColor: isDisabled ? 'warning.main' : 'divider',
        borderRadius: 2,
        backgroundColor: 'background.paper',
        transition: 'all 0.3s ease-in-out',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: (theme) => theme.shadows[12],
          borderColor: isDisabled ? 'warning.main' : 'primary.main',
          borderWidth: isDisabled ? '2px' : '3px',
          backgroundColor: 'action.hover',
        },
        cursor: 'grab',
      }}
    >
      <CardContent sx={{ flexGrow: 1, pb: 0, pt: 2 }}>
        {/* Header: Name + Verified icon + Menu */}
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 0.5 }}>
          <Typography variant="h6" sx={{ flexGrow: 1, fontSize: '1rem', lineHeight: 1.3 }}>
            {playbook.name}
          </Typography>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 1, flexShrink: 0 }}>
            {/* GitHub commit status icon */}
            {playbook.last_committed_at && (() => {
              const committed = new Date(playbook.last_committed_at).getTime();
              const modified = playbook.last_modified ? new Date(playbook.last_modified).getTime() : 0;
              const isClean = committed >= modified;
              return (
                <Tooltip title={isClean
                  ? `Committed ${new Date(playbook.last_committed_at).toLocaleString()}`
                  : `Unsaved changes since last commit (${new Date(playbook.last_committed_at).toLocaleString()})`
                }>
                  <GitHubIcon sx={{ fontSize: 16, color: isClean ? 'success.main' : 'error.main' }} />
                </Tooltip>
              );
            })()}

            {/* Verified icon (only shown for verified playbooks) */}
            {playbook.verified && (
              <Tooltip title="Verified">
                <CheckCircleIcon color="success" sx={{ fontSize: 18 }} />
              </Tooltip>
            )}

            {/* Menu Button */}
            {onExport && (
              <IconButton
                size="small"
                onClick={(e) => setMenuAnchor(e.currentTarget)}
                sx={{ p: 0.25 }}
              >
                <MoreVertIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
        </Box>

        {/* Version + Update indicator */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
          <Typography variant="caption" color="text.secondary">
            {versionText}
          </Typography>
          {availableUpdate && (
            <Tooltip title={
              availableUpdate.release_notes
                ? `Update to v${availableUpdate.latest_version}: ${availableUpdate.release_notes}`
                : `Update available: v${availableUpdate.latest_version}`
            }>
              <Chip
                icon={<UpdateIcon sx={{ fontSize: '14px !important' }} />}
                label={`v${availableUpdate.latest_version}`}
                size="small"
                color={availableUpdate.is_major_update ? 'warning' : 'info'}
                variant="outlined"
                onClick={(e) => {
                  e.stopPropagation();
                  updatePlaybookMutation.mutate();
                }}
                disabled={updatePlaybookMutation.isPending}
                sx={{ height: 20, fontSize: '0.7rem', cursor: 'pointer' }}
              />
            </Tooltip>
          )}
        </Box>

        {/* Description - 2 lines max */}
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            mb: 1,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            lineHeight: 1.4,
            minHeight: '2.8em',
          }}
        >
          {playbook.description}
        </Typography>
      </CardContent>

      {/* Action Buttons */}
      <CardActions sx={{ pt: 0, pb: 1, gap: 1, flexWrap: 'wrap' }}>
        <Tooltip title="Configure parameters for this playbook">
          <span style={{ flex: 1, minWidth: scheduleMode ? '100px' : 'auto' }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={<ConfigureIcon />}
              onClick={() => onConfigure(playbook)}
              fullWidth
              disabled={isDisabled}
              aria-label={`Configure ${playbook.name} playbook`}
            >
              Configure
            </Button>
          </span>
        </Tooltip>

        {scheduleMode && (
          <Tooltip title="Set up a schedule for this playbook">
            <span style={{ flex: 1, minWidth: '100px' }}>
              <Button
                size="small"
                variant="outlined"
                color="secondary"
                startIcon={<ScheduleIcon />}
                onClick={() => setScheduleDialogOpen(true)}
                fullWidth
                disabled={isDisabled}
                aria-label={`Schedule ${playbook.name} playbook`}
              >
                Schedule
              </Button>
            </span>
          </Tooltip>
        )}

        <Tooltip title={
          isDisabled ? 'Enable this playbook first' :
          !selectedCredential ? 'Select a global credential first (in header dropdown)' :
          paramsConfigured ? `Execute with credential: ${selectedCredential.name}` :
          'Configure required parameters first'
        }>
          <span style={{ flex: 1 }}>
            <Button
              size="small"
              variant="contained"
              startIcon={<PlayIcon />}
              onClick={handleExecuteClick}
              fullWidth
              disabled={isDisabled || !paramsConfigured}
              aria-label={`Execute ${playbook.name} playbook`}
            >
              Execute
            </Button>
          </span>
        </Tooltip>
      </CardActions>

      {/* Expandable Details Toggle */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          py: 0.25,
          borderTop: '1px solid',
          borderColor: 'divider',
          '&:hover': { bgcolor: 'action.hover' },
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
          Details
        </Typography>
        <ExpandMoreIcon
          fontSize="small"
          sx={{
            color: 'text.secondary',
            fontSize: 16,
            transition: 'transform 0.2s',
            transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
          }}
        />
      </Box>

      {/* Expandable Details Content */}
      <Collapse in={expanded}>
        <Box sx={{ px: 2, pb: 1.5, pt: 0.5 }}>
          {/* Steps & Params chips */}
          <Box sx={{ display: 'flex', gap: 0.5, mb: 1, flexWrap: 'wrap' }}>
            <Chip
              label={`${playbook.step_count} steps`}
              size="small"
              variant="outlined"
            />
            {playbook.parameter_count > 0 && (
              <Tooltip title={paramsConfigured ? 'Parameters configured' : 'Parameters need configuration'}>
                <Chip
                  icon={paramsConfigured ? <CheckCircleIcon /> : <NotConfiguredIcon />}
                  label="params"
                  size="small"
                  color={paramsConfigured ? 'success' : 'default'}
                  variant="outlined"
                />
              </Tooltip>
            )}
          </Box>

          {/* Debug Mode Toggle */}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <DebugIcon fontSize="small" color={debugMode ? 'primary' : 'disabled'} sx={{ fontSize: 16 }} />
              <FormControlLabel
                control={
                  <Switch
                    checked={debugMode}
                    onChange={handleDebugModeToggle}
                    size="small"
                    color="primary"
                  />
                }
                label={
                  <Typography variant="caption" color={debugMode ? 'primary' : 'text.secondary'}>
                    Debug
                  </Typography>
                }
                sx={{ m: 0 }}
              />
            </Box>

            {/* Schedule Mode Toggle */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <ScheduleIcon fontSize="small" color={scheduleMode ? 'secondary' : 'disabled'} sx={{ fontSize: 16 }} />
              <FormControlLabel
                control={
                  <Switch
                    checked={scheduleMode}
                    onChange={handleScheduleModeToggle}
                    size="small"
                    color="secondary"
                  />
                }
                label={
                  <Typography variant="caption" color={scheduleMode ? 'secondary' : 'text.secondary'}>
                    Schedule
                  </Typography>
                }
                sx={{ m: 0 }}
              />
            </Box>
          </Box>
        </Box>
      </Collapse>

      {/* Menu for all options */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={() => setMenuAnchor(null)}
      >
        {/* Show Details */}
        <MenuItem
          onClick={() => {
            setMenuAnchor(null);
            setDetailsDialogOpen(true);
          }}
        >
          <InfoIcon fontSize="small" sx={{ mr: 1 }} />
          Show Details
        </MenuItem>

        {/* Clear Saved Config */}
        {savedConfig && Object.keys(savedConfig.parameters).length > 0 && (
          <MenuItem
            onClick={() => {
              localStorage.removeItem(STORAGE_KEYS.PLAYBOOK_CONFIG(playbook.path));
              setSavedConfig(null);
              setMenuAnchor(null);
              setSnackbarMessage('Saved configuration cleared');
              setSnackbarOpen(true);
            }}
          >
            <ClearIcon fontSize="small" sx={{ mr: 1 }} />
            Clear Saved Config
          </MenuItem>
        )}

        <Divider />

        {/* Edit Playbook Metadata */}
        <MenuItem onClick={handleOpenEditDialog}>
          <EditIcon fontSize="small" sx={{ mr: 1 }} />
          Edit Name/Description
        </MenuItem>

        {/* Edit Steps & YAML */}
        {onEditPlaybook && (
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onEditPlaybook(playbook);
            }}
          >
            <CodeIcon fontSize="small" sx={{ mr: 1 }} />
            Edit Steps & YAML
          </MenuItem>
        )}

        {/* Duplicate Playbook */}
        <MenuItem
          onClick={handleOpenDuplicateDialog}
          disabled={duplicateMutation.isPending}
        >
          <DuplicateIcon fontSize="small" sx={{ mr: 1 }} />
          Duplicate Playbook
        </MenuItem>

        <Divider />

        {/* Verify/Unverify */}
        {playbook.verified ? (
          <MenuItem
            onClick={() => unverifyMutation.mutate()}
            disabled={unverifyMutation.isPending}
          >
            <VerifiedIcon fontSize="small" sx={{ mr: 1 }} />
            Remove Verification
          </MenuItem>
        ) : (
          <MenuItem
            onClick={() => verifyMutation.mutate()}
            disabled={verifyMutation.isPending}
          >
            <VerifiedIcon fontSize="small" sx={{ mr: 1 }} />
            Mark as Verified
          </MenuItem>
        )}

        {/* Enable/Disable */}
        {playbook.enabled ? (
          <MenuItem
            onClick={() => disableMutation.mutate()}
            disabled={disableMutation.isPending}
          >
            <DisableIcon fontSize="small" sx={{ mr: 1 }} />
            Disable Playbook
          </MenuItem>
        ) : (
          <MenuItem
            onClick={() => enableMutation.mutate()}
            disabled={enableMutation.isPending}
          >
            <EnableIcon fontSize="small" sx={{ mr: 1 }} />
            Enable Playbook
          </MenuItem>
        )}

        <Divider />

        {/* View All Steps */}
        {onViewSteps && (
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onViewSteps(playbook);
            }}
          >
            <ViewStepsIcon fontSize="small" sx={{ mr: 1 }} />
            View All Steps
          </MenuItem>
        )}

        {/* Export */}
        <MenuItem
          onClick={() => {
            setMenuAnchor(null);
            onExport?.(playbook);
          }}
        >
          <DownloadIcon fontSize="small" sx={{ mr: 1 }} />
          Export Playbook
        </MenuItem>

        {/* Submit to Library */}
        {onSubmitToLibrary && (
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onSubmitToLibrary(playbook);
            }}
          >
            <StoreIcon fontSize="small" sx={{ mr: 1 }} />
            Submit to Public Library
          </MenuItem>
        )}

        {/* Push to Private Repo */}
        {onPushToPrivateRepo && (
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onPushToPrivateRepo(playbook);
            }}
          >
            <GitHubIcon fontSize="small" sx={{ mr: 1 }} />
            Push to Private Repo
          </MenuItem>
        )}

        {/* Move to Section */}
        {sections && onMoveToSection && (
          <MenuItem
            onClick={(e) => setSectionMenuAnchor(e.currentTarget)}
          >
            <MoveIcon fontSize="small" sx={{ mr: 1 }} />
            Move to Section
          </MenuItem>
        )}

        <Divider />

        {/* Delete Playbook */}
        <MenuItem
          onClick={() => {
            if (window.confirm(`Are you sure you want to delete "${playbook.name}"? This cannot be undone.`)) {
              deleteMutation.mutate();
            }
          }}
          disabled={deleteMutation.isPending}
          sx={{ color: 'error.main' }}
        >
          <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
          Delete Playbook
        </MenuItem>
      </Menu>

      {/* Edit Dialog */}
      <Dialog
        open={editDialogOpen}
        onClose={() => setEditDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Edit Playbook</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <TextField
              label="Playbook Name"
              value={editedName}
              onChange={(e) => setEditedName(e.target.value)}
              fullWidth
              variant="outlined"
              size="small"
            />
            <TextField
              label="Description"
              value={editedDescription}
              onChange={(e) => setEditedDescription(e.target.value)}
              fullWidth
              multiline
              rows={3}
              variant="outlined"
              size="small"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)} startIcon={<CancelIcon />}>
            Cancel
          </Button>
          <Button
            onClick={handleSaveEdit}
            variant="contained"
            startIcon={<SaveIcon />}
            disabled={updateMetadataMutation.isPending || (editedName === playbook.name && editedDescription === playbook.description)}
          >
            {updateMetadataMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Duplicate Dialog */}
      <Dialog
        open={duplicateDialogOpen}
        onClose={() => setDuplicateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Duplicate Playbook</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Creating a copy of: <strong>{playbook.name}</strong>
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Location: {playbook.path.split('/')[0]}/
            </Typography>
            <TextField
              label="New Playbook Name"
              value={duplicateName}
              onChange={(e) => setDuplicateName(e.target.value)}
              fullWidth
              variant="outlined"
              size="small"
              placeholder="Leave empty for auto-generated name"
              helperText="Enter a new name or leave empty to use auto-generated name"
              autoFocus
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDuplicateDialogOpen(false)} startIcon={<CancelIcon />}>
            Cancel
          </Button>
          <Button
            onClick={handleDuplicate}
            variant="contained"
            startIcon={<DuplicateIcon />}
            disabled={duplicateMutation.isPending}
          >
            {duplicateMutation.isPending ? 'Duplicating...' : 'Duplicate'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Details Dialog */}
      <Dialog
        open={detailsDialogOpen}
        onClose={() => setDetailsDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{playbook.name} - Details</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary" fontWeight="bold">
              Steps ({playbook.step_count}):
            </Typography>
            <List dense sx={{ py: 0 }}>
              {playbook.steps && playbook.steps.length > 0 ? (
                playbook.steps.map((step, index) => (
                  <ListItem key={step.id} sx={{ py: 0.5 }}>
                    <ListItemText
                      primary={
                        <Typography variant="caption" color="text.secondary">
                          {index + 1}. {step.name}
                        </Typography>
                      }
                      secondary={
                        <Typography variant="caption" color="text.secondary">
                          Type: {step.type} | Timeout: {step.timeout}s
                        </Typography>
                      }
                    />
                  </ListItem>
                ))
              ) : (
                <ListItem sx={{ py: 0.5 }}>
                  <ListItemText
                    primary={
                      <Typography variant="caption" color="text.secondary">
                        {playbook.step_count} step(s)
                      </Typography>
                    }
                  />
                </ListItem>
              )}
            </List>

            {playbook.parameter_count > 0 && (
              <>
                <Typography variant="caption" color="text.secondary" fontWeight="bold" sx={{ mt: 2 }}>
                  Required Parameters:
                </Typography>
                <List dense sx={{ py: 0 }}>
                  <ListItem sx={{ py: 0.5 }}>
                    <ListItemText
                      primary={
                        <Typography variant="caption" color="text.secondary">
                          Gateway URL
                        </Typography>
                      }
                    />
                  </ListItem>
                  <ListItem sx={{ py: 0.5 }}>
                    <ListItemText
                      primary={
                        <Typography variant="caption" color="text.secondary">
                          Gateway Credentials
                        </Typography>
                      }
                    />
                  </ListItem>
                </List>
              </>
            )}

            {playbook.verified && playbook.verified_at && (
              <Box sx={{ mt: 2, p: 1, bgcolor: 'success.dark', borderRadius: 1 }}>
                <Typography variant="caption" color="success.light" fontWeight="bold">
                  Verified
                </Typography>
                <Typography variant="caption" color="success.light" sx={{ display: 'block' }}>
                  At: {new Date(playbook.verified_at).toLocaleString()}
                </Typography>
              </Box>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailsDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Schedule Dialog */}
      <ScheduleDialog
        open={scheduleDialogOpen}
        onClose={() => setScheduleDialogOpen(false)}
        playbook={playbook}
        savedConfig={savedConfig}
      />

      {/* Section submenu */}
      {sections && onMoveToSection && (
        <Menu
          anchorEl={sectionMenuAnchor}
          open={Boolean(sectionMenuAnchor)}
          onClose={() => setSectionMenuAnchor(null)}
        >
          <MenuItem disabled sx={{ opacity: '0.7 !important', fontSize: '0.8rem', minHeight: 'auto', py: 0.5 }}>
            Move to section
          </MenuItem>
          <MenuItem
            onClick={() => {
              onMoveToSection(playbook.path, null);
              setSectionMenuAnchor(null);
              setMenuAnchor(null);
            }}
          >
            Unsorted
          </MenuItem>
          <Divider />
          {sections.map((section) => (
            <MenuItem
              key={section.id}
              onClick={() => {
                onMoveToSection(playbook.path, section.id);
                setSectionMenuAnchor(null);
                setMenuAnchor(null);
              }}
            >
              {section.name}
            </MenuItem>
          ))}
        </Menu>
      )}

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={TIMING.UI.SNACKBAR_CARD}
        onClose={() => setSnackbarOpen(false)}
        message={snackbarMessage}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      />
    </Card>
  );
}
