/**
 * Custom hook for managing user-created playbook sections.
 *
 * Sections are persisted to the backend (/api/config/sections/{domain}) so
 * they survive private-browsing sessions, different browsers, and app restarts.
 * Local state is updated immediately (optimistic) and the API call is
 * fire-and-forget, keeping the UX synchronous.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { api } from '../api/client';

export interface PlaybookSection {
  id: string;
  name: string;
  expanded: boolean;
  playbooks: string[]; // playbook paths
}

interface PlaybookSectionsState {
  sections: PlaybookSection[];
  loading: boolean;
  createSection: (name: string) => void;
  deleteSection: (sectionId: string) => void;
  renameSection: (sectionId: string, newName: string) => void;
  toggleSection: (sectionId: string) => void;
  movePlaybook: (playbookPath: string, sectionId: string | null) => void;
  reorderSections: (newSections: PlaybookSection[]) => void;
  reorderPlaybooksInSection: (sectionId: string, newPlaybooks: string[]) => void;
  getUnsortedPlaybooks: (allPaths: string[]) => string[];
}

export function usePlaybookSections(domain: string): PlaybookSectionsState {
  const [sections, setSections] = useState<PlaybookSection[]>([]);
  const [loading, setLoading] = useState(true);
  // Keep a ref so persist() always has the latest domain without stale closure
  const domainRef = useRef(domain);
  domainRef.current = domain;

  // Load from backend on mount and when domain changes
  useEffect(() => {
    setLoading(true);
    fetch(`${api.getBaseUrl()}/api/config/sections/${encodeURIComponent(domain)}`)
      .then(r => r.json())
      .then(data => setSections(data.sections ?? []))
      .catch(() => setSections([]))
      .finally(() => setLoading(false));
  }, [domain]);

  // Optimistic update + background sync
  const persist = useCallback((newSections: PlaybookSection[]) => {
    setSections(newSections);
    // Fire-and-forget — don't block the UI
    fetch(
      `${api.getBaseUrl()}/api/config/sections/${encodeURIComponent(domainRef.current)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sections: newSections }),
      }
    ).catch(() => {
      // Swallow — the worst case is the user loses the change if the backend
      // is unreachable, which will be obvious on next reload.
    });
  }, []);

  const createSection = useCallback((name: string) => {
    const newSection: PlaybookSection = {
      id: `sec-${Date.now()}`,
      name,
      expanded: true,
      playbooks: [],
    };
    persist([...sections, newSection]);
  }, [sections, persist]);

  const deleteSection = useCallback((sectionId: string) => {
    persist(sections.filter(s => s.id !== sectionId));
  }, [sections, persist]);

  const renameSection = useCallback((sectionId: string, newName: string) => {
    persist(sections.map(s => s.id === sectionId ? { ...s, name: newName } : s));
  }, [sections, persist]);

  const toggleSection = useCallback((sectionId: string) => {
    persist(sections.map(s => s.id === sectionId ? { ...s, expanded: !s.expanded } : s));
  }, [sections, persist]);

  const movePlaybook = useCallback((playbookPath: string, sectionId: string | null) => {
    persist(sections.map(s => {
      const filtered = s.playbooks.filter(p => p !== playbookPath);
      if (s.id === sectionId) return { ...s, playbooks: [...filtered, playbookPath] };
      return { ...s, playbooks: filtered };
    }));
  }, [sections, persist]);

  const reorderSections = useCallback((newSections: PlaybookSection[]) => {
    persist(newSections);
  }, [persist]);

  const reorderPlaybooksInSection = useCallback((sectionId: string, newPlaybooks: string[]) => {
    persist(sections.map(s => s.id === sectionId ? { ...s, playbooks: newPlaybooks } : s));
  }, [sections, persist]);

  const getUnsortedPlaybooks = useCallback((allPaths: string[]): string[] => {
    const assigned = new Set(sections.flatMap(s => s.playbooks));
    return allPaths.filter(p => !assigned.has(p));
  }, [sections]);

  return {
    sections,
    loading,
    createSection,
    deleteSection,
    renameSection,
    toggleSection,
    movePlaybook,
    reorderSections,
    reorderPlaybooksInSection,
    getUnsortedPlaybooks,
  };
}
