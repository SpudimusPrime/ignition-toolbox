/**
 * DraggableStepList - Reorderable list of playbook steps
 *
 * Uses @dnd-kit for drag-and-drop reordering with visual feedback.
 * Each step can be expanded to edit, deleted, or duplicated.
 */

import {
  Box,
  Paper,
  Typography,
  IconButton,
  Tooltip,
  Chip,
  Collapse,
} from '@mui/material';
import {
  DragIndicator as DragIcon,
  Delete as DeleteIcon,
  ContentCopy as DuplicateIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Edit as EditIcon,
} from '@mui/icons-material';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { StepTypeInfo, CredentialInfo } from '../types/api';
import { StepEditorPanel } from './StepEditorPanel';

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

interface DraggableStepListProps {
  steps: StepConfig[];
  stepTypes: StepTypeInfo[];
  credentials: CredentialInfo[];
  onStepsChange: (steps: StepConfig[]) => void;
  onEditStep: (index: number) => void;
  editingIndex: number | null;
}

// Domain colors for visual distinction
const DOMAIN_COLORS: Record<string, string> = {
  gateway: '#4caf50',
  browser: '#2196f3',
  designer: '#9c27b0',
  perspective: '#ff9800',
  utility: '#607d8b',
  playbook: '#795548',
  fat: '#f44336',
};

export function DraggableStepList({
  steps,
  stepTypes,
  credentials,
  onStepsChange,
  onEditStep,
  editingIndex,
}: DraggableStepListProps) {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = steps.findIndex((s) => s.id === active.id);
      const newIndex = steps.findIndex((s) => s.id === over.id);
      onStepsChange(arrayMove(steps, oldIndex, newIndex));
    }
  };

  const handleDeleteStep = (index: number) => {
    const newSteps = [...steps];
    newSteps.splice(index, 1);
    onStepsChange(newSteps);
  };

  const handleDuplicateStep = (index: number) => {
    const step = steps[index];
    const newStep: StepConfig = {
      ...step,
      id: `${step.id}_copy`,
      name: `${step.name} (Copy)`,
      parameters: { ...step.parameters },
    };
    const newSteps = [...steps];
    newSteps.splice(index + 1, 0, newStep);
    onStepsChange(newSteps);
  };

  const handleStepChange = (index: number, updatedStep: StepConfig) => {
    const newSteps = [...steps];
    newSteps[index] = updatedStep;
    onStepsChange(newSteps);
  };

  const getStepType = (typeString: string): StepTypeInfo | undefined => {
    return stepTypes.find((st) => st.type === typeString);
  };

  const getDomain = (typeString: string): string => {
    return typeString.split('.')[0] || 'unknown';
  };

  if (steps.length === 0) {
    return (
      <Box
        sx={{
          p: 4,
          textAlign: 'center',
          border: '2px dashed',
          borderColor: 'divider',
          borderRadius: 1,
        }}
      >
        <Typography color="text.secondary">
          No steps yet. Click "Add Step" to create your first step.
        </Typography>
      </Box>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext
        items={steps.map((s) => s.id)}
        strategy={verticalListSortingStrategy}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {steps.map((step, index) => (
            <SortableStepItem
              key={step.id}
              step={step}
              index={index}
              stepType={getStepType(step.type)}
              domain={getDomain(step.type)}
              credentials={credentials}
              isEditing={editingIndex === index}
              onEdit={() => onEditStep(index)}
              onDelete={() => handleDeleteStep(index)}
              onDuplicate={() => handleDuplicateStep(index)}
              onChange={(updatedStep) => handleStepChange(index, updatedStep)}
            />
          ))}
        </Box>
      </SortableContext>
    </DndContext>
  );
}

// Individual sortable step item
function SortableStepItem({
  step,
  index,
  stepType,
  domain,
  credentials,
  isEditing,
  onEdit,
  onDelete,
  onDuplicate,
  onChange,
}: {
  step: StepConfig;
  index: number;
  stepType: StepTypeInfo | undefined;
  domain: string;
  credentials: CredentialInfo[];
  isEditing: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onChange: (step: StepConfig) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const domainColor = DOMAIN_COLORS[domain] || '#757575';

  return (
    <Paper
      ref={setNodeRef}
      style={style}
      elevation={isDragging ? 4 : 1}
      sx={{
        borderLeft: 4,
        borderLeftColor: domainColor,
        bgcolor: 'background.paper',
      }}
    >
      {/* Step Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          p: 1,
          gap: 1,
          cursor: 'pointer',
        }}
        onClick={onEdit}
      >
        {/* Drag Handle */}
        <Box
          {...attributes}
          {...listeners}
          sx={{
            display: 'flex',
            cursor: 'grab',
            color: 'text.secondary',
            '&:active': { cursor: 'grabbing' },
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <DragIcon />
        </Box>

        {/* Step Number */}
        <Chip
          label={index + 1}
          size="small"
          sx={{
            minWidth: 28,
            bgcolor: domainColor,
            color: 'white',
            fontWeight: 600,
          }}
        />

        {/* Step Info */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>
              {step.name || step.id}
            </Typography>
            <Chip
              label={step.type}
              size="small"
              variant="outlined"
              sx={{ fontSize: '0.65rem', height: 20 }}
            />
          </Box>
          {stepType && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: 'block' }}
              noWrap
            >
              {stepType.description}
            </Typography>
          )}
        </Box>

        {/* Actions */}
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          <Tooltip title="Edit step">
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); onEdit(); }}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Duplicate step">
            <IconButton size="small" onClick={(e) => { e.stopPropagation(); onDuplicate(); }}>
              <DuplicateIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete step">
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              sx={{ color: 'error.main' }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); onEdit(); }}>
            {isEditing ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>
      </Box>

      {/* Expanded Editor */}
      <Collapse in={isEditing}>
        <Box sx={{ p: 2, pt: 0, borderTop: 1, borderTopColor: 'divider' }}>
          <StepEditorPanel
            stepType={stepType || null}
            step={step}
            credentials={credentials}
            onChange={onChange}
          />
        </Box>
      </Collapse>
    </Paper>
  );
}
