/**
 * StepTypeSelector - Searchable autocomplete for selecting step types
 *
 * Organizes step types by domain with type-to-filter search.
 */

import { useMemo } from 'react';
import { Autocomplete, TextField, Typography, Box } from '@mui/material';
import type { StepTypeInfo } from '../types/api';

interface StepTypeSelectorProps {
  stepTypes: StepTypeInfo[];
  value: string;
  onChange: (stepType: string) => void;
  disabled?: boolean;
}

const DOMAIN_CONFIG: Record<string, { label: string; icon: string }> = {
  gateway:     { label: 'Gateway',       icon: '🔧' },
  browser:     { label: 'Browser',       icon: '🌐' },
  designer:    { label: 'Designer',      icon: '🎨' },
  perspective: { label: 'Perspective',   icon: '📱' },
  utility:     { label: 'Utility',       icon: '⚙️' },
  playbook:    { label: 'Playbook',      icon: '📋' },
  fat:         { label: 'FAT Reporting', icon: '📊' },
};

const DOMAIN_ORDER = ['gateway', 'browser', 'designer', 'perspective', 'utility', 'playbook', 'fat'];

export function StepTypeSelector({
  stepTypes,
  value,
  onChange,
  disabled = false,
}: StepTypeSelectorProps) {
  const sortedStepTypes = useMemo(() => {
    return [...stepTypes].sort((a, b) => {
      const ai = DOMAIN_ORDER.indexOf(a.domain);
      const bi = DOMAIN_ORDER.indexOf(b.domain);
      const domainDiff = (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      return domainDiff !== 0 ? domainDiff : a.type.localeCompare(b.type);
    });
  }, [stepTypes]);

  const selectedOption = sortedStepTypes.find((st) => st.type === value) ?? null;

  return (
    <Autocomplete
      options={sortedStepTypes}
      groupBy={(option) => option.domain}
      getOptionLabel={(option) => option.type}
      value={selectedOption}
      onChange={(_, newValue) => onChange(newValue?.type ?? '')}
      disabled={disabled}
      isOptionEqualToValue={(option, val) => option.type === val.type}
      filterOptions={(options, { inputValue }) => {
        const q = inputValue.toLowerCase();
        return options.filter(
          (opt) =>
            opt.type.toLowerCase().includes(q) ||
            opt.description.toLowerCase().includes(q)
        );
      }}
      renderInput={(params) => (
        <TextField {...params} label="Step Type" size="small" placeholder="Search step types…" />
      )}
      renderOption={(props, option) => (
        <li {...props} key={option.type}>
          <Box sx={{ display: 'flex', flexDirection: 'column', py: 0.25 }}>
            <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {option.type}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
              {option.description}
            </Typography>
          </Box>
        </li>
      )}
      renderGroup={(params) => {
        const cfg = DOMAIN_CONFIG[params.group] ?? { icon: '📦', label: params.group };
        return (
          <li key={params.key}>
            <Box
              sx={{
                px: 2,
                py: 0.5,
                bgcolor: 'background.paper',
                fontWeight: 600,
                fontSize: '0.8rem',
                color: 'text.secondary',
                position: 'sticky',
                top: -8,
                zIndex: 1,
              }}
            >
              {cfg.icon} {cfg.label}
            </Box>
            <ul style={{ padding: 0 }}>{params.children}</ul>
          </li>
        );
      }}
    />
  );
}
