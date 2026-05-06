/**
 * Playbooks page - List and execute playbooks organized by category
 */

import { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Alert,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Button,
  IconButton,
  Tooltip,
  Snackbar,
  Alert as MuiAlert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Upload as UploadIcon,
  Refresh as RefreshIcon,
  DragIndicator as DragIcon,
  Add as AddIcon,
  Store as StoreIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  CreateNewFolder as NewSectionIcon,
} from '@mui/icons-material';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
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
import { api } from '../api/client';
import { createLogger } from '../utils/logger';
import { TIMING } from '../config/timing';
import { STORAGE_KEYS, STORAGE_PREFIXES } from '../utils/localStorage';
import { PlaybookCard } from '../components/PlaybookCard';

const logger = createLogger('Playbooks');
import { PlaybookExecutionDialog } from '../components/PlaybookExecutionDialog';
import { PlaybookStepsDialog } from '../components/PlaybookStepsDialog';
import { PlaybookLibraryDialog } from '../components/PlaybookLibraryDialog';

import { PlaybookEditorDialog } from '../components/PlaybookEditorDialog';
import { CreatePlaybookDialog } from '../components/CreatePlaybookDialog';
import { SubmitToLibraryDialog } from '../components/SubmitToLibraryDialog';
import { PushToPrivateRepoDialog } from '../components/PushToPrivateRepoDialog';
import { useStore } from '../store';
import { useCategoryOrder, useCategoryExpanded } from '../hooks/usePlaybookOrder';
import { usePlaybookSections } from '../hooks/usePlaybookSections';
import type { PlaybookInfo } from '../types/api';

// Extracted modules
import { categorizePlaybooks, domainNames } from './PlaybookCategorySection';
import { createCategoryDragEndHandler } from './PlaybookDragHandlers';
import {
  handleExport as doExport,
  handleImport as doImport,
} from './PlaybookImportExport';

// Stable empty array used as the default value for the playbooks query result.
// Using a module-level constant avoids creating a new [] reference on every
// render during the loading phase, which would cause useEffect([playbooks]) to
// fire on every render and produce an infinite setState → re-render loop.
const EMPTY_PLAYBOOKS: PlaybookInfo[] = [];

// Sortable playbook card wrapper
function SortablePlaybookCard({ playbook, onConfigure, onExecute, onExport, onViewSteps, onEditPlaybook, onSubmitToLibrary, onPushToPrivateRepo, dragEnabled, availableUpdate, sections, onMoveToSection }: {
  playbook: PlaybookInfo;
  onConfigure: (playbook: PlaybookInfo) => void;
  onExecute?: (playbook: PlaybookInfo) => void;
  onExport?: (playbook: PlaybookInfo) => void;
  onViewSteps?: (playbook: PlaybookInfo) => void;
  onEditPlaybook?: (playbook: PlaybookInfo) => void;
  onSubmitToLibrary?: (playbook: PlaybookInfo) => void;
  onPushToPrivateRepo?: (playbook: PlaybookInfo) => void;
  dragEnabled: boolean;
  availableUpdate?: { latest_version: string; is_major_update: boolean; release_notes: string | null };
  sections?: Array<{ id: string; name: string }>;
  onMoveToSection?: (playbookPath: string, sectionId: string | null) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: playbook.path, disabled: !dragEnabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    cursor: dragEnabled ? 'grab' : 'default',
  };

  return (
    <div ref={setNodeRef} style={style} {...(dragEnabled ? attributes : {})} {...(dragEnabled ? listeners : {})}>
      <PlaybookCard
        playbook={playbook}
        onConfigure={onConfigure}
        onExecute={onExecute}
        onExport={onExport}
        onViewSteps={onViewSteps}
        onEditPlaybook={onEditPlaybook}
        onSubmitToLibrary={onSubmitToLibrary}
        onPushToPrivateRepo={onPushToPrivateRepo}
        availableUpdate={availableUpdate}
        sections={sections}
        onMoveToSection={onMoveToSection}
      />
    </div>
  );
}

// Sortable accordion wrapper for category reordering
function SortableAccordion({
  categoryId,
  expanded,
  onChange,
  dragEnabled,
  title,
  children,
  onRename,
  onDelete,
}: {
  categoryId: string;
  expanded: boolean;
  onChange: (event: React.SyntheticEvent, isExpanded: boolean) => void;
  dragEnabled: boolean;
  title: string;
  children: React.ReactNode;
  onRename?: () => void;
  onDelete?: () => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: categoryId, disabled: !dragEnabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style}>
      <Accordion expanded={expanded} onChange={onChange}>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          sx={{
            minHeight: '32px !important',
            '& .MuiAccordionSummary-content': { my: '6px !important', display: 'flex', alignItems: 'center', gap: 1 }
          }}
        >
          {dragEnabled && (
            <Box
              {...attributes}
              {...listeners}
              sx={{
                display: 'flex',
                alignItems: 'center',
                cursor: 'grab',
                mr: 1,
                '&:active': { cursor: 'grabbing' }
              }}
            >
              <DragIcon fontSize="small" />
            </Box>
          )}
          <Typography variant="h6" sx={{ fontSize: '1.1rem', flexGrow: 1 }}>{title}</Typography>
          {onRename && (
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); onRename(); }}
              sx={{ p: 0.25 }}
            >
              <EditIcon fontSize="small" />
            </IconButton>
          )}
          {onDelete && (
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              sx={{ p: 0.25, color: 'error.main' }}
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          )}
        </AccordionSummary>
        <AccordionDetails>
          {children}
        </AccordionDetails>
      </Accordion>
    </div>
  );
}

// Droppable zone wrapper for section drop targets
function DroppableZone({ id, children }: { id: string; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <Box
      ref={setNodeRef}
      sx={{
        minHeight: 48,
        p: 0.5,
        borderRadius: 1,
        transition: 'all 0.2s ease',
        border: '2px dashed transparent',
        ...(isOver && {
          bgcolor: 'rgba(59, 130, 246, 0.1)',
          borderColor: 'primary.main',
        }),
      }}
    >
      {children}
    </Box>
  );
}

// Inline utility functions (getPlaybookOrder, savePlaybookOrder, applyOrder,
// categorizePlaybooks, splitByVerification) have been extracted to:
// - PlaybookDragHandlers.ts
// - PlaybookCategorySection.tsx

interface PlaybooksProps {
  domainFilter?: 'gateway' | 'designer' | 'perspective';
}

export function Playbooks({ domainFilter }: PlaybooksProps) {
  const setActiveExecutionId = useStore((state) => state.setActiveExecutionId);
  const setPlaybookSubTab = useStore((state) => state.setPlaybookSubTab);
  const queryClient = useQueryClient();
  const gap = 2;
  const gridSpacing = 2;
  const playbookGridColumns = useStore((state) => state.playbookGridColumns);

  // Snackbar notification state
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'warning' | 'info';
  }>({ open: false, message: '', severity: 'info' });

  const showNotification = (message: string, severity: 'success' | 'error' | 'warning' | 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  // Generate responsive grid columns based on max setting
  const getGridColumns = (forCategory = false) => {
    const max = forCategory ? Math.max(3, playbookGridColumns - 1) : playbookGridColumns;
    return {
      xs: '1fr',
      sm: 'repeat(2, 1fr)',
      md: `repeat(${Math.min(3, max)}, 1fr)`,
      lg: `repeat(${Math.min(forCategory ? 3 : 4, max)}, 1fr)`,
      xl: `repeat(${max}, 1fr)`,
    };
  };
  const [selectedPlaybook, setSelectedPlaybook] = useState<PlaybookInfo | null>(null);
  const [dragEnabled, setDragEnabled] = useState(false);
  const [stepsDialogPlaybook, setStepsDialogPlaybook] = useState<PlaybookInfo | null>(null);
  const [editorPlaybook, setEditorPlaybook] = useState<PlaybookInfo | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [libraryDialogOpen, setLibraryDialogOpen] = useState(false);
  const [submitPlaybook, setSubmitPlaybook] = useState<PlaybookInfo | null>(null);
  const [privateRepoPlaybook, setPrivateRepoPlaybook] = useState<PlaybookInfo | null>(null);
  const [sectionNameDialog, setSectionNameDialog] = useState<{
    open: boolean;
    title: string;
    value: string;
    onConfirm: (name: string) => void;
  }>({ open: false, title: '', value: '', onConfirm: () => {} });

  // Section management (per-domain, only used in filtered view)
  const sectionsDomain = domainFilter || 'gateway';
  const {
    sections,
    loading: sectionsLoading,
    createSection,
    deleteSection,
    renameSection,
    toggleSection,
    movePlaybook,
    reorderSections,
    getUnsortedPlaybooks,
  } = usePlaybookSections(sectionsDomain);

  // Category order and expanded state (managed by hooks with localStorage persistence)
  const { order: rawCategoryOrder, updateOrder: updateCategoryOrder } = useCategoryOrder();
  const categoryOrder = rawCategoryOrder.length > 0 ? rawCategoryOrder : ['gateway', 'designer', 'perspective'];
  const { expanded: categoryExpanded, setExpanded: setCategoryExpanded } = useCategoryExpanded();

  // Fetch playbooks
  const { data: playbooks = EMPTY_PLAYBOOKS, isLoading, error } = useQuery<PlaybookInfo[]>({
    queryKey: ['playbooks'],
    queryFn: api.playbooks.list,
    refetchInterval: TIMING.POLLING.PLAYBOOKS, // Refetch every 30 seconds
  });

  // Fetch available updates for card-level indicators
  interface UpdateInfo {
    latest_version: string;
    is_major_update: boolean;
    release_notes: string | null;
  }
  const { data: updateMap } = useQuery({
    queryKey: ['playbook-updates'],
    queryFn: async () => {
      const response = await fetch(`${api.getBaseUrl()}/api/playbooks/updates`);
      if (!response.ok) return new Map<string, UpdateInfo>();
      const data = await response.json();
      const map = new Map<string, UpdateInfo>();
      for (const update of data.updates || []) {
        map.set(update.playbook_path, {
          latest_version: update.latest_version,
          is_major_update: update.is_major_update,
          release_notes: update.release_notes,
        });
      }
      return map;
    },
    refetchInterval: TIMING.POLLING.PLAYBOOK_UPDATES, // Refetch every 5 minutes
  });

  // Categorize playbooks
  const categories = useMemo(() => categorizePlaybooks(playbooks), [playbooks]);

  // State for each category to enable re-rendering on drag
  const [gatewayPlaybooks, setGatewayPlaybooks] = useState(categories.gateway);
  const [designerPlaybooks, setDesignerPlaybooks] = useState(categories.designer);
  const [perspectivePlaybooks, setPerspectivePlaybooks] = useState(categories.perspective);

  // Update state when playbooks change
  useEffect(() => {
    setGatewayPlaybooks(categories.gateway);
    setDesignerPlaybooks(categories.designer);
    setPerspectivePlaybooks(categories.perspective);

    // Clean up saved configurations for deleted playbooks
    if (playbooks.length > 0) {
      const validPaths = new Set(playbooks.map(p => p.path));
      const keysToRemove: string[] = [];

      // Find all localStorage keys for playbook configurations
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith(STORAGE_PREFIXES.PLAYBOOK_CONFIG) || key?.startsWith(STORAGE_PREFIXES.PLAYBOOK_DEBUG) || key?.startsWith(STORAGE_PREFIXES.PLAYBOOK_ORDER)) {
          // Extract playbook path from key
          if (key.startsWith(STORAGE_PREFIXES.PLAYBOOK_CONFIG)) {
            const playbookPath = key.replace(STORAGE_PREFIXES.PLAYBOOK_CONFIG, '');
            if (!validPaths.has(playbookPath)) {
              keysToRemove.push(key);
              // Also remove associated debug mode setting
              keysToRemove.push(STORAGE_KEYS.PLAYBOOK_DEBUG(playbookPath));
            }
          }
        }
      }

      // Remove invalid configurations
      keysToRemove.forEach(key => {
        localStorage.removeItem(key);
        logger.debug(`Removed stale configuration: ${key}`);
      });

      if (keysToRemove.length > 0) {
        logger.debug(`Cleaned up ${keysToRemove.length} stale playbook configurations`);
      }
    }
  }, [playbooks, categories]);

  // Configure drag sensors with activation distance to prevent accidental drags
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleConfigure = (playbook: PlaybookInfo) => {
    setSelectedPlaybook(playbook);
  };

  const handleExecute = async (playbook: PlaybookInfo) => {
    // v3.45.2 - Non-blocking execution with immediate navigation
    // Get global selected credential
    const selectedCredential = useStore.getState().selectedCredential;

    // Get saved configuration from localStorage
    const savedConfigStr = localStorage.getItem(STORAGE_KEYS.PLAYBOOK_CONFIG(playbook.path));

    // Get debug mode preference
    const debugModeStr = localStorage.getItem(STORAGE_KEYS.PLAYBOOK_DEBUG(playbook.path));
    const debug_mode = debugModeStr === 'true';

    // If global credential is selected, execute directly with it
    if (selectedCredential && !savedConfigStr) {
      logger.debug('Executing playbook with credential:', {
        playbook_path: playbook.path,
        credential_name: selectedCredential.name,
        gateway_url: selectedCredential.gateway_url,
        debug_mode,
      });

      // Start execution (don't await - let it run in background)
      api.executions.start({
        playbook_path: playbook.path,
        parameters: {}, // Backend will auto-fill from credential
        gateway_url: selectedCredential.gateway_url,
        credential_name: selectedCredential.name,
        debug_mode,
      }).then(response => {
        logger.info('Execution started successfully:', response);
        // Switch to execution detail sub-tab AFTER getting execution ID
        setActiveExecutionId(response.execution_id);
        setPlaybookSubTab('active-execution');
      }).catch(error => {
        logger.error('Failed to execute playbook:', error);
        logger.error('Error details:', error instanceof Error ? error.message : String(error));
        if (error && typeof error === 'object' && 'data' in error) {
          logger.error('Error data:', (error as { data: unknown }).data);
        }
        showNotification(`Failed to start execution: ${error instanceof Error ? error.message : String(error)}`, 'error');
      });

      // Return immediately without waiting - navigation will happen when API responds
      return;
    }

    if (!savedConfigStr) {
      // No saved config and no global credential - open configure dialog
      setSelectedPlaybook(playbook);
      return;
    }

    // If we have saved config but no credential, open configure dialog
    if (!selectedCredential) {
      setSelectedPlaybook(playbook);
      return;
    }

    try {
      const savedConfig = JSON.parse(savedConfigStr);

      // Convert string values to their declared types
      const convertedParams: Record<string, string | boolean | number> = {};
      for (const [key, value] of Object.entries(savedConfig.parameters || {})) {
        const paramDef = playbook.parameters.find(p => p.name === key);
        if (paramDef?.type === 'boolean') {
          convertedParams[key] = value === 'true' || value === true;
        } else if (paramDef?.type === 'integer') {
          const parsed = parseInt(value as string, 10);
          convertedParams[key] = isNaN(parsed) ? value as string : parsed;
        } else if (paramDef?.type === 'float') {
          const parsed = parseFloat(value as string);
          convertedParams[key] = isNaN(parsed) ? value as string : parsed;
        } else {
          convertedParams[key] = value as string;
        }
      }

      // Execute with saved config parameters + global credential (don't await - navigate when ready)
      api.executions.start({
        playbook_path: playbook.path,
        parameters: convertedParams as Record<string, string | boolean | number>,
        gateway_url: selectedCredential.gateway_url, // Always use global credential's gateway_url
        credential_name: selectedCredential.name, // Always use global credential
        debug_mode,
        timeout_overrides: savedConfig.timeoutOverrides, // Include timeout overrides from saved config
      }).then(response => {
        // Switch to execution detail sub-tab AFTER getting execution ID
        setActiveExecutionId(response.execution_id);
        setPlaybookSubTab('active-execution');
      }).catch(error => {
        logger.error('Failed to execute playbook:', error);
        showNotification('Failed to start execution. Please check the console for details.', 'error');
      });
    } catch (error) {
      logger.error('Failed to parse saved config:', error);
      showNotification('Failed to load saved configuration. Please try again.', 'error');
    }
  };

  // Unified drag end handlers using parameterized factory (replaces 3 identical handlers)
  const handleGatewayDragEnd = createCategoryDragEndHandler(gatewayPlaybooks, setGatewayPlaybooks, 'gateway');
  const handleDesignerDragEnd = createCategoryDragEndHandler(designerPlaybooks, setDesignerPlaybooks, 'designer');
  const handlePerspectiveDragEnd = createCategoryDragEndHandler(perspectivePlaybooks, setPerspectivePlaybooks, 'perspective');

  // Handle category reordering
  const handleCategoryDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = categoryOrder.indexOf(active.id as string);
      const newIndex = categoryOrder.indexOf(over.id as string);
      const newOrder = arrayMove(categoryOrder, oldIndex, newIndex);
      updateCategoryOrder(newOrder);
    }
  };

  // Handle category expand/collapse
  const handleCategoryExpandChange = (categoryId: string) => (
    _event: React.SyntheticEvent,
    isExpanded: boolean
  ) => {
    setCategoryExpanded(categoryId, isExpanded);
  };

  const handleViewSteps = (playbook: PlaybookInfo) => {
    setStepsDialogPlaybook(playbook);
  };

  const handleEditPlaybook = (playbook: PlaybookInfo) => {
    setEditorPlaybook(playbook);
  };

  // Delegate to extracted modules (import/export/reset use snackbar + queryClient)
  const handleExport = (playbook: PlaybookInfo) => {
    doExport(playbook, showNotification);
  };

  const handleImport = () => {
    doImport(showNotification, queryClient);
  };

  const handleSubmitToLibrary = (playbook: PlaybookInfo) => {
    setSubmitPlaybook(playbook);
  };

  const handlePushToPrivateRepo = (playbook: PlaybookInfo) => {
    setPrivateRepoPlaybook(playbook);
  };

  const handleMoveToSection = (playbookPath: string, sectionId: string | null) => {
    movePlaybook(playbookPath, sectionId);
  };

  const handleNewSection = () => {
    setSectionNameDialog({
      open: true,
      title: 'New Section',
      value: '',
      onConfirm: (name) => createSection(name),
    });
  };

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['playbooks'] });
    queryClient.invalidateQueries({ queryKey: ['playbook-updates'] });
  };

  // Get filtered playbooks based on domainFilter prop
  const getFilteredPlaybooks = () => {
    if (!domainFilter) return null;
    switch (domainFilter) {
      case 'gateway': return gatewayPlaybooks;
      case 'designer': return designerPlaybooks;
      case 'perspective': return perspectivePlaybooks;
      default: return null;
    }
  };

  const filteredPlaybooks = getFilteredPlaybooks();

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, py: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 2 }}>
          <Typography variant="h5" sx={{ fontSize: '1.3rem' }}>
            {domainFilter ? `${domainNames[domainFilter]} Playbooks` : 'Playbooks'}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
            {domainFilter
              ? `${filteredPlaybooks?.length || 0} playbooks available`
              : 'Select a playbook to configure and execute'}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', gap: 1 }}>
          <Tooltip title="Browse and install playbooks from repository">
            <Button
              variant="contained"
              startIcon={<StoreIcon />}
              onClick={() => setLibraryDialogOpen(true)}
              size="small"
              color="secondary"
            >
              Browse Library
            </Button>
          </Tooltip>

          <Tooltip title="Create a new playbook from template">
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
              size="small"
              color="primary"
            >
              Create New
            </Button>
          </Tooltip>

          <Tooltip title={dragEnabled ? "Disable drag mode" : "Enable drag mode to reorder playbooks"}>
            <Button
              variant={dragEnabled ? "contained" : "outlined"}
              startIcon={<DragIcon />}
              onClick={() => setDragEnabled(!dragEnabled)}
              size="small"
              color={dragEnabled ? "success" : "primary"}
            >
              {dragEnabled ? "Drag Mode ON" : "Drag Mode"}
            </Button>
          </Tooltip>

          {domainFilter && (
            <Tooltip title="Create a new section to organize playbooks">
              <Button
                variant="outlined"
                startIcon={<NewSectionIcon />}
                onClick={handleNewSection}
                size="small"
              >
                New Section
              </Button>
            </Tooltip>
          )}

          <Tooltip title="Import playbook from JSON export">
            <Button
              variant="outlined"
              startIcon={<UploadIcon />}
              onClick={handleImport}
              size="small"
            >
              Import
            </Button>
          </Tooltip>

          <Tooltip title="Refresh playbook list">
            <IconButton
              onClick={handleRefresh}
              size="small"
              color="primary"
            >
              <RefreshIcon />
            </IconButton>
          </Tooltip>

        </Box>
      </Box>

      {/* Loading state */}
      {isLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress aria-label="Loading playbooks" />
        </Box>
      )}

      {/* Error state */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to load playbooks: {(error as Error).message}
        </Alert>
      )}

      {/* Empty state */}
      {!isLoading && !error && playbooks.length === 0 && (
        <Alert severity="info">
          No playbooks found. Add YAML playbooks to the ./playbooks directory.
        </Alert>
      )}

      {/* Empty state for filtered domain */}
      {!isLoading && !error && domainFilter && filteredPlaybooks && filteredPlaybooks.length === 0 && (
        <Alert severity="info">
          No {domainNames[domainFilter]} playbooks found. Create one or browse the library.
        </Alert>
      )}

      {/* Filtered Domain View (single domain, with user sections) */}
      {!isLoading && !error && domainFilter && filteredPlaybooks && filteredPlaybooks.length > 0 && (() => {
        const allPaths = filteredPlaybooks.map(p => p.path);
        const unsortedPaths = getUnsortedPlaybooks(allPaths);
        const unsortedPlaybooks = filteredPlaybooks.filter(p => unsortedPaths.includes(p.path));
        const sectionMeta = sections.map(s => ({ id: s.id, name: s.name }));

        // Helper: find which section a playbook belongs to (null = unsorted)
        const findPlaybookSection = (path: string): string | null => {
          const section = sections.find(s => s.playbooks.includes(path));
          return section?.id || null;
        };

        // Unified drag handler: supports reordering within containers AND moving between sections
        const handleSectionDragEnd = (event: DragEndEvent) => {
          const { active, over } = event;
          if (!over) return;

          const activeId = String(active.id);
          const overId = String(over.id);
          if (activeId === overId) return;

          // Check if active item is a playbook path (contains '/')
          const isPlaybookDrag = activeId.includes('/');

          if (isPlaybookDrag) {
            const activeSectionId = findPlaybookSection(activeId);
            let targetSectionId: string | null | undefined = undefined; // undefined = no move

            if (overId.startsWith('drop-')) {
              // Dropped on a droppable zone
              targetSectionId = overId === 'drop-unsorted' ? null : overId.replace('drop-', '');
            } else if (overId.includes('/')) {
              // Dropped on another playbook card — find its section
              const overSectionId = findPlaybookSection(overId);
              if (overSectionId !== activeSectionId) {
                targetSectionId = overSectionId;
              }
              // Same section: no cross-section move needed
            } else {
              // Dropped on a section accordion header (section ID without 'drop-' prefix)
              const matchedSection = sections.find(s => s.id === overId);
              if (matchedSection) {
                targetSectionId = matchedSection.id;
              }
            }

            if (targetSectionId !== undefined && targetSectionId !== activeSectionId) {
              movePlaybook(activeId, targetSectionId);
            }
          } else {
            // Section reordering
            const oldIndex = sections.findIndex(s => s.id === activeId);
            const newIndex = sections.findIndex(s => s.id === overId);
            if (oldIndex !== -1 && newIndex !== -1) {
              reorderSections(arrayMove(sections, oldIndex, newIndex));
            }
          }
        };

        return (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleSectionDragEnd}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap }}>
            {/* Unsorted playbooks - only show when there are unsorted playbooks or in drag mode */}
            {(unsortedPlaybooks.length > 0 || dragEnabled) && (
            <DroppableZone id="drop-unsorted">
              <Box>
                <Typography variant="subtitle1" sx={{ fontSize: '0.95rem', fontWeight: 500, mb: 1.5 }}>
                  Unsorted ({unsortedPlaybooks.length})
                </Typography>
                {unsortedPlaybooks.length > 0 ? (
                  <SortableContext items={unsortedPlaybooks.map(p => p.path)} strategy={verticalListSortingStrategy}>
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: getGridColumns(),
                        gap: gridSpacing,
                      }}
                    >
                      {unsortedPlaybooks.map((playbook) => (
                        <SortablePlaybookCard
                          key={playbook.path}
                          playbook={playbook}
                          onConfigure={handleConfigure}
                          onExecute={handleExecute}
                          onExport={handleExport}
                          onViewSteps={handleViewSteps}
                          onEditPlaybook={handleEditPlaybook}
                          onSubmitToLibrary={handleSubmitToLibrary}
                          onPushToPrivateRepo={handlePushToPrivateRepo}
                          dragEnabled={dragEnabled}
                          availableUpdate={updateMap?.get(playbook.path.replace('.yaml', '').replace('.yml', ''))}
                          sections={sectionMeta}
                          onMoveToSection={handleMoveToSection}
                        />
                      ))}
                    </Box>
                  </SortableContext>
                ) : (
                  <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                    Drag playbooks here to unassign from sections.
                  </Typography>
                )}
              </Box>
            </DroppableZone>
            )}

            {/* User sections */}
            <SortableContext items={sections.map(s => s.id)} strategy={verticalListSortingStrategy}>
              {sections.map((section) => {
                const sectionPlaybooks = filteredPlaybooks.filter(p => section.playbooks.includes(p.path));

                return (
                  <SortableAccordion
                    key={section.id}
                    categoryId={section.id}
                    expanded={section.expanded}
                    onChange={() => toggleSection(section.id)}
                    dragEnabled={dragEnabled}
                    title={`${section.name} (${sectionPlaybooks.length})`}
                    onRename={() => {
                      setSectionNameDialog({
                        open: true,
                        title: 'Rename Section',
                        value: section.name,
                        onConfirm: (name) => renameSection(section.id, name),
                      });
                    }}
                    onDelete={() => {
                      if (window.confirm(`Delete section "${section.name}"? Playbooks will move to Unsorted.`)) {
                        deleteSection(section.id);
                      }
                    }}
                  >
                    <DroppableZone id={`drop-${section.id}`}>
                      {sectionPlaybooks.length > 0 ? (
                        <SortableContext items={sectionPlaybooks.map(p => p.path)} strategy={verticalListSortingStrategy}>
                          <Box
                            sx={{
                              display: 'grid',
                              gridTemplateColumns: getGridColumns(),
                              gap: gridSpacing,
                            }}
                          >
                            {sectionPlaybooks.map((playbook) => (
                              <SortablePlaybookCard
                                key={playbook.path}
                                playbook={playbook}
                                onConfigure={handleConfigure}
                                onExecute={handleExecute}
                                onExport={handleExport}
                                onViewSteps={handleViewSteps}
                                onEditPlaybook={handleEditPlaybook}
                                onSubmitToLibrary={handleSubmitToLibrary}
                                onPushToPrivateRepo={handlePushToPrivateRepo}
                                dragEnabled={dragEnabled}
                                availableUpdate={updateMap?.get(playbook.path.replace('.yaml', '').replace('.yml', ''))}
                                sections={sectionMeta}
                                onMoveToSection={handleMoveToSection}
                              />
                            ))}
                          </Box>
                        </SortableContext>
                      ) : (
                        <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                          Drag playbooks here or use card menu &rarr; Move to Section
                        </Typography>
                      )}
                    </DroppableZone>
                  </SortableAccordion>
                );
              })}
            </SortableContext>
          </Box>
          </DndContext>
        );
      })()}

      {/* Organized Playbook Sections (all domains, with accordions) */}
      {!isLoading && !error && !domainFilter && (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleCategoryDragEnd}>
          <SortableContext items={categoryOrder} strategy={verticalListSortingStrategy}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap }}>
              {categoryOrder.map((categoryId) => {
                // Category configuration
                const categoryConfig = {
                  gateway: {
                    title: `🔧 Gateway (${gatewayPlaybooks.length})`,
                    playbooks: gatewayPlaybooks,
                    dragHandler: handleGatewayDragEnd,
                    emptyMessage: 'No Gateway playbooks found. Add YAML playbooks to ./playbooks/gateway/',
                  },
                  designer: {
                    title: `🎨 Designer (${designerPlaybooks.length})`,
                    playbooks: designerPlaybooks,
                    dragHandler: handleDesignerDragEnd,
                    emptyMessage: 'No Designer playbooks found. Add YAML playbooks to ./playbooks/designer/',
                  },
                  perspective: {
                    title: `📱 Perspective (${perspectivePlaybooks.length})`,
                    playbooks: perspectivePlaybooks,
                    dragHandler: handlePerspectiveDragEnd,
                    emptyMessage: 'No Perspective playbooks found. Add YAML playbooks to ./playbooks/perspective/ or ./playbooks/browser/',
                  },
                }[categoryId];

                if (!categoryConfig) return null;

                return (
                  <SortableAccordion
                    key={categoryId}
                    categoryId={categoryId}
                    expanded={categoryExpanded[categoryId] ?? true}
                    onChange={handleCategoryExpandChange(categoryId)}
                    dragEnabled={dragEnabled}
                    title={categoryConfig.title}
                  >
                    {categoryConfig.playbooks.length > 0 ? (
                      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={categoryConfig.dragHandler}>
                        <SortableContext items={categoryConfig.playbooks.map(p => p.path)} strategy={verticalListSortingStrategy}>
                          <Box
                            sx={{
                              display: 'grid',
                              gridTemplateColumns: getGridColumns(true),
                              gap: gridSpacing,
                            }}
                          >
                            {categoryConfig.playbooks.map((playbook) => (
                              <SortablePlaybookCard
                                key={playbook.path}
                                playbook={playbook}
                                onConfigure={handleConfigure}
                                onExecute={handleExecute}
                                onExport={handleExport}
                                onViewSteps={handleViewSteps}
                                onEditPlaybook={handleEditPlaybook}
                                onSubmitToLibrary={handleSubmitToLibrary}
                                onPushToPrivateRepo={handlePushToPrivateRepo}
                                dragEnabled={dragEnabled}
                                availableUpdate={updateMap?.get(playbook.path.replace('.yaml', '').replace('.yml', ''))}
                              />
                            ))}
                          </Box>
                        </SortableContext>
                      </DndContext>
                    ) : (
                      <Alert severity="info">
                        {categoryConfig.emptyMessage}
                      </Alert>
                    )}
                  </SortableAccordion>
                );
              })}
            </Box>
          </SortableContext>
        </DndContext>
      )}

      {/* Execution dialog */}
      <PlaybookExecutionDialog
        open={selectedPlaybook !== null}
        playbook={selectedPlaybook}
        onClose={() => setSelectedPlaybook(null)}
      />

      {/* Steps dialog */}
      <PlaybookStepsDialog
        open={stepsDialogPlaybook !== null}
        playbook={stepsDialogPlaybook}
        onClose={() => setStepsDialogPlaybook(null)}
      />

      {/* Create New Playbook Dialog */}
      <CreatePlaybookDialog
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        defaultDomain={domainFilter || 'gateway'}
        queryClient={queryClient}
        showNotification={showNotification}
      />

      {/* Playbook Library Dialog */}
      <PlaybookLibraryDialog
        open={libraryDialogOpen}
        onClose={() => setLibraryDialogOpen(false)}
      />

      {/* Submit to Library Dialog */}
      <SubmitToLibraryDialog
        open={submitPlaybook !== null}
        onClose={() => setSubmitPlaybook(null)}
        playbook={submitPlaybook}
      />

      {/* Push to Private Repo Dialog */}
      <PushToPrivateRepoDialog
        open={privateRepoPlaybook !== null}
        onClose={() => setPrivateRepoPlaybook(null)}
        playbook={privateRepoPlaybook}
      />

      {/* Playbook Editor Dialog (Form-based) */}
      <PlaybookEditorDialog
        open={editorPlaybook !== null}
        playbook={editorPlaybook}
        onClose={() => setEditorPlaybook(null)}
        onSaved={() => {
          // Optionally refresh the playbooks list
        }}
      />

      {/* Section Name Dialog (create/rename) */}
      <Dialog
        open={sectionNameDialog.open}
        onClose={() => setSectionNameDialog(prev => ({ ...prev, open: false }))}
        maxWidth="xs"
        fullWidth
        disableRestoreFocus
      >
        <DialogTitle>{sectionNameDialog.title}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            label="Section name"
            value={sectionNameDialog.value}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              setSectionNameDialog(prev => ({ ...prev, value: e.target.value }))
            }
            onKeyDown={(e) => {
              if (e.key === 'Enter' && sectionNameDialog.value.trim()) {
                sectionNameDialog.onConfirm(sectionNameDialog.value.trim());
                setSectionNameDialog(prev => ({ ...prev, open: false }));
              }
            }}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSectionNameDialog(prev => ({ ...prev, open: false }))}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={!sectionNameDialog.value.trim()}
            onClick={() => {
              sectionNameDialog.onConfirm(sectionNameDialog.value.trim());
              setSectionNameDialog(prev => ({ ...prev, open: false }));
            }}
          >
            {sectionNameDialog.title === 'New Section' ? 'Create' : 'Rename'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <MuiAlert
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
          severity={snackbar.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </MuiAlert>
      </Snackbar>

    </Box>
  );
}
