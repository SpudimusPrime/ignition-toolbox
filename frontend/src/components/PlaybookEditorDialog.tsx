/**
 * PlaybookEditorDialog - Visual playbook editor with form and YAML views
 *
 * Features:
 * - Form-based step editing with dynamic parameter inputs
 * - Drag-and-drop step reordering
 * - Toggle between Form and YAML views
 * - Live YAML preview
 * - Parameter editing
 * - Save with backup
 */

import { useState, useEffect, useMemo } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  TextField,
  Tabs,
  Tab,
  IconButton,
  Alert,
  CircularProgress,
  Divider,
  Chip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import {
  Close as CloseIcon,
  Save as SaveIcon,
  Add as AddIcon,
  Code as CodeIcon,
  ViewList as FormIcon,
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { PlaybookInfo, CredentialInfo } from '../types/api';
import { StepTypeSelector } from './StepTypeSelector';
import { DraggableStepList } from './DraggableStepList';
import { createLogger } from '../utils/logger';
import yaml from 'js-yaml';

const logger = createLogger('PlaybookEditorDialog');

interface RawYamlPlaybook {
  name?: string;
  version?: string;
  description?: string;
  domain?: string;
  parameters?: RawYamlParam[];
  steps?: RawYamlStep[];
  metadata?: Record<string, unknown>;
}
interface RawYamlParam {
  name: string;
  type?: string;
  required?: boolean;
  default?: string;
  description?: string;
}
interface RawYamlStep {
  id: string;
  name?: string;
  type: string;
  parameters?: Record<string, unknown>;
  timeout?: number;
  retry_count?: number;
  retry_delay?: number;
  on_failure?: string;
  skip_if?: string;
}

interface StepConfig {
  id: string;
  name: string;
  type: string;
  parameters: Record<string, unknown>;
  timeout?: number;
  retry_count?: number;
  retry_delay?: number;
  on_failure?: string;
  skip_if?: string;
}

interface ParameterConfig {
  name: string;
  type: string;
  required: boolean;
  default?: string;
  description?: string;
}

interface PlaybookConfig {
  name: string;
  version: string;
  description: string;
  domain: string;
  parameters: ParameterConfig[];
  steps: StepConfig[];
  metadata?: Record<string, unknown>;
}

interface PlaybookEditorDialogProps {
  open: boolean;
  playbook: PlaybookInfo | null;
  onClose: () => void;
  onSaved?: () => void;
}

export function PlaybookEditorDialog({
  open,
  playbook,
  onClose,
  onSaved,
}: PlaybookEditorDialogProps) {
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<'form' | 'yaml'>('form');
  const [config, setConfig] = useState<PlaybookConfig | null>(null);
  const [yamlContent, setYamlContent] = useState('');
  const [editingStepIndex, setEditingStepIndex] = useState<number | null>(null);
  const [newStepType, setNewStepType] = useState('');
  const [showAddStep, setShowAddStep] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Fetch step types
  const { data: stepTypesData, isLoading: stepTypesLoading } = useQuery({
    queryKey: ['step-types'],
    queryFn: api.playbooks.getStepTypes,
    staleTime: 1000 * 60 * 5, // Cache for 5 minutes
  });

  // Fetch credentials for credential parameters
  const { data: credentials = [] } = useQuery<CredentialInfo[]>({
    queryKey: ['credentials'],
    queryFn: api.credentials.list,
  });

  // Fetch playbook YAML content when dialog opens
  const { data: exportData, isLoading: playbookLoading } = useQuery({
    queryKey: ['playbook-export', playbook?.path],
    queryFn: () => (playbook ? api.playbooks.export(playbook.path) : null),
    enabled: open && !!playbook,
  });

  // Parse YAML to config when export data loads
  useEffect(() => {
    if (exportData?.yaml_content) {
      try {
        const parsed = yaml.load(exportData.yaml_content) as RawYamlPlaybook;
        const newConfig: PlaybookConfig = {
          name: parsed.name || playbook?.name || '',
          version: parsed.version || '1.0',
          description: parsed.description || '',
          domain: parsed.domain || playbook?.domain || 'gateway',
          parameters: (parsed.parameters || []).map((p: RawYamlParam) => ({
            name: p.name,
            type: p.type || 'string',
            required: p.required !== false,
            default: p.default,
            description: p.description,
          })),
          steps: (parsed.steps || []).map((s: RawYamlStep) => ({
            id: s.id,
            name: s.name || s.id,
            type: s.type,
            parameters: s.parameters || {},
            timeout: s.timeout,
            retry_count: s.retry_count,
            retry_delay: s.retry_delay,
            on_failure: s.on_failure,
            skip_if: s.skip_if,
          })),
          metadata: parsed.metadata,
        };
        setConfig(newConfig);
        setYamlContent(exportData.yaml_content);
        setHasChanges(false);
        setError(null);
      } catch (e) {
        logger.error('Failed to parse playbook YAML:', e);
        setError(`Failed to parse playbook: ${e}`);
        setYamlContent(exportData.yaml_content);
      }
    }
  }, [exportData, playbook]);

  // Convert config to YAML
  const configToYaml = useMemo(() => {
    if (!config) return '';
    try {
      const yamlObj: Record<string, unknown> = {
        name: config.name,
        version: config.version,
        description: config.description,
        domain: config.domain,
      };

      if (config.parameters.length > 0) {
        yamlObj.parameters = config.parameters.map((p) => {
          const param: Record<string, unknown> = {
            name: p.name,
            type: p.type,
            required: p.required,
          };
          if (p.default !== undefined) param.default = p.default;
          if (p.description) param.description = p.description;
          return param;
        });
      }

      if (config.steps.length > 0) {
        yamlObj.steps = config.steps.map((s) => {
          const step: Record<string, unknown> = {
            id: s.id,
            name: s.name,
            type: s.type,
          };
          if (Object.keys(s.parameters).length > 0) step.parameters = s.parameters;
          if (s.timeout !== undefined && s.timeout !== 300) step.timeout = s.timeout;
          if (s.retry_count !== undefined && s.retry_count > 0) step.retry_count = s.retry_count;
          if (s.retry_delay !== undefined && s.retry_delay !== 5) step.retry_delay = s.retry_delay;
          if (s.on_failure !== undefined && s.on_failure !== 'abort') step.on_failure = s.on_failure;
          if (s.skip_if) step.skip_if = s.skip_if;
          return step;
        });
      }

      if (config.metadata) {
        yamlObj.metadata = config.metadata;
      }

      return yaml.dump(yamlObj, { lineWidth: -1, quotingType: '"' });
    } catch (e) {
      logger.error('Failed to convert config to YAML:', e);
      return '';
    }
  }, [config]);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!playbook) throw new Error('No playbook selected');
      const yamlToSave = viewMode === 'yaml' ? yamlContent : configToYaml;
      return api.playbooks.update(playbook.path, yamlToSave);
    },
    onSuccess: (result) => {
      logger.info('Playbook saved:', result);
      setHasChanges(false);
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      queryClient.invalidateQueries({ queryKey: ['playbook-export', playbook?.path] });
      onSaved?.();
    },
    onError: (error) => {
      logger.error('Failed to save playbook:', error);
      setError(`Failed to save: ${error}`);
    },
  });

  // Handle config changes
  const handleConfigChange = (updates: Partial<PlaybookConfig>) => {
    if (!config) return;
    setConfig({ ...config, ...updates });
    setHasChanges(true);
  };

  // Handle steps change
  const handleStepsChange = (steps: StepConfig[]) => {
    handleConfigChange({ steps });
  };

  // Add new step
  const handleAddStep = () => {
    if (!newStepType || !config) return;
    const stepType = stepTypesData?.step_types.find((st) => st.type === newStepType);
    const stepId = `step${config.steps.length + 1}`;
    const newStep: StepConfig = {
      id: stepId,
      name: stepType?.description || stepId,
      type: newStepType,
      parameters: {},
      timeout: 300,
      on_failure: 'abort',
    };
    handleConfigChange({ steps: [...config.steps, newStep] });
    setShowAddStep(false);
    setNewStepType('');
    setEditingStepIndex(config.steps.length); // Edit the new step
  };

  // Handle YAML changes
  const handleYamlChange = (newYaml: string) => {
    setYamlContent(newYaml);
    setHasChanges(true);
    setError(null);
  };

  // Parse YAML to config when switching to form view
  const handleViewChange = (newView: 'form' | 'yaml') => {
    if (viewMode === 'yaml' && newView === 'form') {
      try {
        const parsed = yaml.load(yamlContent) as RawYamlPlaybook;
        const newConfig: PlaybookConfig = {
          name: parsed.name || '',
          version: parsed.version || '1.0',
          description: parsed.description || '',
          domain: parsed.domain || 'gateway',
          parameters: (parsed.parameters || []).map((p: RawYamlParam) => ({
            name: p.name,
            type: p.type || 'string',
            required: p.required !== false,
            default: p.default,
            description: p.description,
          })),
          steps: (parsed.steps || []).map((s: RawYamlStep) => ({
            id: s.id,
            name: s.name || s.id,
            type: s.type,
            parameters: s.parameters || {},
            timeout: s.timeout,
            retry_count: s.retry_count,
            retry_delay: s.retry_delay,
            on_failure: s.on_failure,
            skip_if: s.skip_if,
          })),
          metadata: parsed.metadata,
        };
        setConfig(newConfig);
        setError(null);
      } catch (e) {
        setError(`Invalid YAML syntax: ${e}`);
        return; // Don't switch views if YAML is invalid
      }
    } else if (viewMode === 'form' && newView === 'yaml') {
      setYamlContent(configToYaml);
    }
    setViewMode(newView);
  };

  // Close handler
  const handleClose = () => {
    if (hasChanges) {
      const confirm = window.confirm('You have unsaved changes. Discard them?');
      if (!confirm) return;
    }
    setConfig(null);
    setYamlContent('');
    setHasChanges(false);
    setError(null);
    setEditingStepIndex(null);
    setShowAddStep(false);
    onClose();
  };

  const isLoading = stepTypesLoading || playbookLoading;
  const stepTypes = stepTypesData?.step_types || [];

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{
        sx: { height: '90vh', maxHeight: 900 },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 2, pb: 1 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6">
            Edit Playbook: {playbook?.name}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {playbook?.path}
          </Typography>
        </Box>

        {/* View Mode Toggle */}
        <Tabs
          value={viewMode}
          onChange={(_, v) => handleViewChange(v)}
          sx={{ minHeight: 36 }}
        >
          <Tab
            value="form"
            label="Form"
            icon={<FormIcon fontSize="small" />}
            iconPosition="start"
            sx={{ minHeight: 36, py: 0 }}
          />
          <Tab
            value="yaml"
            label="YAML"
            icon={<CodeIcon fontSize="small" />}
            iconPosition="start"
            sx={{ minHeight: 36, py: 0 }}
          />
        </Tabs>

        <IconButton onClick={handleClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers sx={{ p: 0 }}>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ m: 2 }}>
            {error}
          </Alert>
        ) : viewMode === 'form' && config ? (
          <Box sx={{ display: 'flex', height: '100%' }}>
            {/* Main content */}
            <Box sx={{ flex: 1, p: 2, overflow: 'auto' }}>
              {/* Playbook Metadata */}
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" sx={{ mb: 1.5, color: 'text.secondary' }}>
                  Playbook Info
                </Typography>
                <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                  <TextField
                    label="Name"
                    value={config.name}
                    onChange={(e) => handleConfigChange({ name: e.target.value })}
                    size="small"
                    sx={{ flex: 2 }}
                  />
                  <TextField
                    label="Version"
                    value={config.version}
                    onChange={(e) => handleConfigChange({ version: e.target.value })}
                    size="small"
                    sx={{ flex: 1 }}
                  />
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Domain</InputLabel>
                    <Select
                      value={config.domain}
                      label="Domain"
                      onChange={(e) => handleConfigChange({ domain: e.target.value })}
                    >
                      <MenuItem value="gateway">Gateway</MenuItem>
                      <MenuItem value="browser">Browser</MenuItem>
                      <MenuItem value="designer">Designer</MenuItem>
                      <MenuItem value="perspective">Perspective</MenuItem>
                    </Select>
                  </FormControl>
                </Box>
                <TextField
                  label="Description"
                  value={config.description}
                  onChange={(e) => handleConfigChange({ description: e.target.value })}
                  size="small"
                  fullWidth
                  multiline
                  rows={2}
                />
              </Box>

              <Divider sx={{ mb: 2 }} />

              {/* Steps Section */}
              <Box sx={{ mb: 2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                  <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
                    Steps ({config.steps.length})
                  </Typography>
                  <Button
                    startIcon={<AddIcon />}
                    size="small"
                    onClick={() => setShowAddStep(!showAddStep)}
                    variant={showAddStep ? 'contained' : 'outlined'}
                  >
                    Add Step
                  </Button>
                </Box>

                {/* Add Step Panel */}
                {showAddStep && (
                  <Box
                    sx={{
                      p: 2,
                      mb: 2,
                      border: 1,
                      borderColor: 'primary.main',
                      borderRadius: 1,
                      bgcolor: 'background.default',
                    }}
                  >
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Select Step Type
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 2 }}>
                      <Box sx={{ flex: 1 }}>
                        <StepTypeSelector
                          stepTypes={stepTypes}
                          value={newStepType}
                          onChange={setNewStepType}
                        />
                      </Box>
                      <Button
                        variant="contained"
                        onClick={handleAddStep}
                        disabled={!newStepType}
                      >
                        Add
                      </Button>
                      <Button onClick={() => setShowAddStep(false)}>
                        Cancel
                      </Button>
                    </Box>
                  </Box>
                )}

                {/* Steps List */}
                <DraggableStepList
                  steps={config.steps}
                  stepTypes={stepTypes}
                  credentials={credentials}
                  onStepsChange={handleStepsChange}
                  onEditStep={(index) =>
                    setEditingStepIndex(editingStepIndex === index ? null : index)
                  }
                  editingIndex={editingStepIndex}
                />
              </Box>
            </Box>

            {/* YAML Preview Sidebar */}
            <Box
              sx={{
                width: 350,
                borderLeft: 1,
                borderColor: 'divider',
                bgcolor: 'background.default',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Box sx={{ p: 1.5, borderBottom: 1, borderColor: 'divider' }}>
                <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
                  YAML Preview
                </Typography>
              </Box>
              <Box
                sx={{
                  flex: 1,
                  overflow: 'auto',
                  p: 1,
                  '& pre': {
                    m: 0,
                    fontSize: '0.75rem',
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                  },
                }}
              >
                <pre>{configToYaml}</pre>
              </Box>
            </Box>
          </Box>
        ) : viewMode === 'yaml' ? (
          <Box sx={{ p: 2, height: '100%' }}>
            <TextField
              multiline
              fullWidth
              value={yamlContent}
              onChange={(e) => handleYamlChange(e.target.value)}
              sx={{
                height: '100%',
                '& .MuiInputBase-root': {
                  height: '100%',
                  alignItems: 'flex-start',
                },
                '& .MuiInputBase-input': {
                  fontFamily: 'monospace',
                  fontSize: '0.85rem',
                  height: '100% !important',
                  overflow: 'auto !important',
                },
              }}
            />
          </Box>
        ) : null}
      </DialogContent>

      <DialogActions sx={{ px: 2, py: 1.5 }}>
        <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
          {hasChanges && (
            <Chip
              label="Unsaved changes"
              size="small"
              color="warning"
              variant="outlined"
            />
          )}
        </Box>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          variant="contained"
          startIcon={<SaveIcon />}
          onClick={() => saveMutation.mutate()}
          disabled={!hasChanges || saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving...' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
