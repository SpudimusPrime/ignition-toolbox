/**
 * StepEditorPanel - Dynamic form for editing step parameters
 *
 * Renders appropriate input controls based on parameter types:
 * - string: TextField
 * - integer/float: TextField with number type
 * - boolean: Switch
 * - credential: Credential selector dropdown
 * - playbook_ref: Searchable dropdown of available playbooks
 * - file: File path input with browse
 * - selector: TextField for CSS selectors
 * - list/dict: TextArea for JSON input
 * - enum (options): Select dropdown
 */

import { useState, useEffect, useRef } from 'react';
import {
  Box,
  TextField,
  FormControl,
  FormLabel,
  Select,
  MenuItem,
  Switch,
  Typography,
  IconButton,
  InputAdornment,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Autocomplete,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Folder as FolderIcon,
  Code as CodeIcon,
  Warning as WarningIcon,
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import type { StepTypeInfo, StepTypeParameter, CredentialInfo, PlaybookInfo } from '../types/api';
import { HelpTooltip } from './HelpTooltip';
import { api } from '../api/client';

interface StepConfig {
  id: string;
  name: string;
  type: string;
  parameters: Record<string, unknown>;
  timeout?: number;
  retry_count?: number;
  retry_delay?: number;
  on_failure?: string;
}

interface StepEditorPanelProps {
  stepType: StepTypeInfo | null;
  step: StepConfig;
  credentials: CredentialInfo[];
  onChange: (step: StepConfig) => void;
}

export function StepEditorPanel({
  stepType,
  step,
  credentials,
  onChange,
}: StepEditorPanelProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Local draft state for ID and Name so that each keystroke doesn't cause
  // the parent to re-key the sortable item and unmount this component.
  // Changes are committed to parent state on blur.
  const [draftId, setDraftId] = useState(step.id);
  const [draftName, setDraftName] = useState(step.name);
  const idFocused = useRef(false);
  const nameFocused = useRef(false);

  // Sync draft when the committed step changes from outside (e.g. step switches)
  useEffect(() => {
    if (!idFocused.current) setDraftId(step.id);
  }, [step.id]);
  useEffect(() => {
    if (!nameFocused.current) setDraftName(step.name);
  }, [step.name]);

  const handleParamChange = (name: string, value: unknown) => {
    onChange({ ...step, parameters: { ...step.parameters, [name]: value } });
  };

  const handleMetaChange = (field: keyof StepConfig, value: StepConfig[keyof StepConfig]) => {
    onChange({ ...step, [field]: value });
  };

  // Fetch available playbooks — only when a playbook_ref parameter is present
  const needsPlaybooks = stepType?.parameters.some((p) => p.type === 'playbook_ref') ?? false;
  const { data: availablePlaybooks = [] } = useQuery<PlaybookInfo[]>({
    queryKey: ['playbooks'],
    queryFn: api.playbooks.list,
    enabled: needsPlaybooks,
    staleTime: 1000 * 60,
  });

  if (!stepType) {
    return (
      <Box sx={{ p: 2, textAlign: 'center' }}>
        <Typography color="text.secondary">
          Select a step type to configure parameters
        </Typography>
      </Box>
    );
  }

  const requiredParams = stepType.parameters.filter((p) => p.required);
  const optionalParams = stepType.parameters.filter((p) => !p.required);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Step ID and Name — use local draft state to prevent focus loss on each keystroke */}
      <Box sx={{ display: 'flex', gap: 2 }}>
        <TextField
          label="Step ID"
          value={draftId}
          onChange={(e) => setDraftId(e.target.value)}
          onFocus={() => { idFocused.current = true; }}
          onBlur={(e) => {
            idFocused.current = false;
            handleMetaChange('id', e.target.value);
          }}
          size="small"
          required
          sx={{ flex: 1 }}
          helperText="Unique identifier (e.g., step1, login_step)"
        />
        <TextField
          label="Step Name"
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          onFocus={() => { nameFocused.current = true; }}
          onBlur={(e) => {
            nameFocused.current = false;
            handleMetaChange('name', e.target.value);
          }}
          size="small"
          required
          sx={{ flex: 2 }}
          helperText="Human-readable name"
        />
      </Box>

      {/* Required Parameters */}
      {requiredParams.length > 0 && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1, color: 'text.secondary' }}>
            Required Parameters
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {requiredParams.map((param) => (
              <ParameterInput
                key={param.name}
                parameter={param}
                value={step.parameters[param.name]}
                credentials={credentials}
                availablePlaybooks={availablePlaybooks}
                onChange={(value) => handleParamChange(param.name, value)}
              />
            ))}
          </Box>
        </Box>
      )}

      {/* Optional Parameters */}
      {optionalParams.length > 0 && (
        <Accordion
          expanded={showAdvanced}
          onChange={(_, expanded) => setShowAdvanced(expanded)}
          sx={{ bgcolor: 'background.default' }}
        >
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
              Optional Parameters ({optionalParams.length})
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {optionalParams.map((param) => (
                <ParameterInput
                  key={param.name}
                  parameter={param}
                  value={step.parameters[param.name] ?? param.default}
                  credentials={credentials}
                  availablePlaybooks={availablePlaybooks}
                  onChange={(value) => handleParamChange(param.name, value)}
                />
              ))}
            </Box>
          </AccordionDetails>
        </Accordion>
      )}

      {/* Step Options */}
      <Accordion sx={{ bgcolor: 'background.default' }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle2" sx={{ color: 'text.secondary' }}>
            Step Options
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            <TextField
              label="Timeout (seconds)"
              type="number"
              value={step.timeout ?? 300}
              onChange={(e) => handleMetaChange('timeout', parseInt(e.target.value) || 300)}
              size="small"
              InputProps={{ inputProps: { min: 1, max: 3600 } }}
              helperText="Maximum time to wait for step completion"
            />
            <Box sx={{ display: 'flex', gap: 2 }}>
              <TextField
                label="Retry Count"
                type="number"
                value={step.retry_count ?? 0}
                onChange={(e) => handleMetaChange('retry_count', parseInt(e.target.value) || 0)}
                size="small"
                sx={{ flex: 1 }}
                InputProps={{ inputProps: { min: 0, max: 10 } }}
                helperText="Number of retries on failure"
              />
              <TextField
                label="Retry Delay (seconds)"
                type="number"
                value={step.retry_delay ?? 5}
                onChange={(e) => handleMetaChange('retry_delay', parseInt(e.target.value) || 5)}
                size="small"
                sx={{ flex: 1 }}
                InputProps={{ inputProps: { min: 1, max: 60 } }}
                helperText="Delay between retries"
              />
            </Box>
            <FormControl fullWidth size="small">
              <FormLabel sx={{ fontSize: '0.75rem', mb: 0.5 }}>On Failure</FormLabel>
              <Select
                value={step.on_failure ?? 'abort'}
                onChange={(e) => handleMetaChange('on_failure', e.target.value)}
              >
                <MenuItem value="abort">Abort - Stop playbook execution</MenuItem>
                <MenuItem value="continue">Continue - Proceed to next step</MenuItem>
                <MenuItem value="rollback">Rollback - Attempt cleanup</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}

function ParameterInput({
  parameter,
  value,
  credentials,
  availablePlaybooks,
  onChange,
}: {
  parameter: StepTypeParameter;
  value: unknown;
  credentials: CredentialInfo[];
  availablePlaybooks: PlaybookInfo[];
  onChange: (value: unknown) => void;
}) {
  const handleBrowseFile = async () => {
    if (window.electronAPI?.openFileDialog) {
      try {
        const result = await window.electronAPI.openFileDialog({
          title: 'Select File',
          properties: ['openFile'],
        });
        if (result && result.length > 0) onChange(result[0]);
      } catch (error) {
        console.error('Failed to open file dialog:', error);
      }
    } else {
      const path = window.prompt('Enter file path:');
      if (path) onChange(path);
    }
  };

  const renderInput = () => {
    if (parameter.options && parameter.options.length > 0) {
      return (
        <Select
          value={value ?? parameter.default ?? ''}
          onChange={(e) => onChange(e.target.value)}
          size="small"
          fullWidth
        >
          {parameter.options.map((option) => (
            <MenuItem key={option} value={option}>{option}</MenuItem>
          ))}
        </Select>
      );
    }

    switch (parameter.type) {
      case 'boolean':
        return (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Switch
              checked={value === true || value === 'true'}
              onChange={(e) => onChange(e.target.checked)}
              size="small"
            />
            <Typography variant="body2">
              {value === true || value === 'true' ? 'True' : 'False'}
            </Typography>
          </Box>
        );

      case 'integer':
        return (
          <TextField
            type="number"
            value={value ?? parameter.default ?? ''}
            onChange={(e) => onChange(parseInt(e.target.value) || 0)}
            size="small"
            fullWidth
            InputProps={{ inputProps: { step: 1 } }}
          />
        );

      case 'float':
        return (
          <TextField
            type="number"
            value={value ?? parameter.default ?? ''}
            onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
            size="small"
            fullWidth
            InputProps={{ inputProps: { step: 0.1 } }}
          />
        );

      case 'credential':
        return (
          <Select
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value)}
            size="small"
            fullWidth
            displayEmpty
          >
            <MenuItem value="" disabled>Select credential...</MenuItem>
            {credentials.map((cred) => (
              <MenuItem key={cred.name} value={cred.name}>
                {cred.name} ({cred.username})
              </MenuItem>
            ))}
          </Select>
        );

      case 'playbook_ref': {
        const verifiedPlaybooks = availablePlaybooks.filter((p) => p.verified);
        const unverifiedPlaybooks = availablePlaybooks.filter((p) => !p.verified);
        const sorted = [...verifiedPlaybooks, ...unverifiedPlaybooks];
        const selected = sorted.find((p) => p.path === value) ?? null;

        return (
          <Autocomplete
            options={sorted}
            groupBy={(p) => (p.verified ? '✓ Verified' : '⚠ Unverified (cannot be nested)')}
            getOptionLabel={(p) => p.path}
            value={selected}
            onChange={(_, newVal) => onChange(newVal?.path ?? '')}
            isOptionEqualToValue={(a, b) => a.path === b.path}
            filterOptions={(options, { inputValue }) => {
              const q = inputValue.toLowerCase();
              return options.filter(
                (p) => p.path.toLowerCase().includes(q) || p.name.toLowerCase().includes(q)
              );
            }}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                placeholder="Search playbooks…"
                helperText={
                  selected && !selected.verified
                    ? 'This playbook must be marked Verified before it can run as a nested step.'
                    : undefined
                }
                FormHelperTextProps={{ sx: { color: 'warning.main' } }}
              />
            )}
            renderOption={(props, option) => (
              <li {...props} key={option.path}>
                <Box sx={{ display: 'flex', flexDirection: 'column', py: 0.25 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    {!option.verified && (
                      <WarningIcon sx={{ fontSize: '0.85rem', color: 'warning.main' }} />
                    )}
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.82rem' }}>
                      {option.path}
                    </Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
                    {option.name}{option.description ? ` — ${option.description}` : ''}
                  </Typography>
                </Box>
              </li>
            )}
          />
        );
      }

      case 'file':
        return (
          <TextField
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value)}
            size="small"
            fullWidth
            placeholder="Enter file path..."
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={handleBrowseFile}
                    edge="end"
                    size="small"
                    title="Browse files"
                    sx={{ color: '#00ff00' }}
                  >
                    <FolderIcon />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        );

      case 'selector':
        return (
          <TextField
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value)}
            size="small"
            fullWidth
            placeholder="CSS selector (e.g., #id, .class, [data-attr])"
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <CodeIcon fontSize="small" sx={{ color: 'text.secondary' }} />
                </InputAdornment>
              ),
            }}
          />
        );

      case 'list':
      case 'dict':
        return (
          <TextField
            value={
              typeof value === 'string'
                ? value
                : JSON.stringify(value ?? (parameter.type === 'list' ? [] : {}), null, 2)
            }
            onChange={(e) => {
              try { onChange(JSON.parse(e.target.value)); }
              catch { onChange(e.target.value); }
            }}
            size="small"
            fullWidth
            multiline
            rows={3}
            placeholder={parameter.type === 'list' ? '["item1", "item2"]' : '{"key": "value"}'}
            sx={{ '& .MuiInputBase-input': { fontFamily: 'monospace', fontSize: '0.8rem' } }}
          />
        );

      case 'string':
      default:
        if (parameter.name === 'script' || parameter.name === 'code') {
          return (
            <TextField
              value={value ?? parameter.default ?? ''}
              onChange={(e) => onChange(e.target.value)}
              size="small"
              fullWidth
              multiline
              rows={4}
              placeholder={parameter.description}
              sx={{ '& .MuiInputBase-input': { fontFamily: 'monospace', fontSize: '0.8rem' } }}
            />
          );
        }
        return (
          <TextField
            value={value ?? parameter.default ?? ''}
            onChange={(e) => onChange(e.target.value)}
            size="small"
            fullWidth
            placeholder={parameter.description}
          />
        );
    }
  };

  return (
    <FormControl fullWidth>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5, gap: 0.5 }}>
        <FormLabel sx={{ fontSize: '0.8rem' }}>
          {parameter.name}
          {parameter.required && <span style={{ color: '#ff4444' }}> *</span>}
        </FormLabel>
        <Chip label={parameter.type} size="small" sx={{ fontSize: '0.65rem', height: 18 }} />
        {parameter.description && (
          <HelpTooltip size="small" content={parameter.description} />
        )}
      </Box>
      {renderInput()}
    </FormControl>
  );
}
