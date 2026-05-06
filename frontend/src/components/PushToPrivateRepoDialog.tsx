/**
 * PushToPrivateRepoDialog - Commit a playbook to the user's private GitHub repo
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Typography,
  Box,
  Alert,
  CircularProgress,
  Chip,
  Link,
} from '@mui/material';
import { GitHub as GitHubIcon, CheckCircle as SuccessIcon } from '@mui/icons-material';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { PlaybookInfo } from '../types/api';

interface PushToPrivateRepoDialogProps {
  open: boolean;
  onClose: () => void;
  playbook: PlaybookInfo | null;
}

interface RepoInfo {
  configured: boolean;
  repo_url?: string;
  folder?: string;
  token_preview?: string;
}

export function PushToPrivateRepoDialog({ open, onClose, playbook }: PushToPrivateRepoDialogProps) {
  const queryClient = useQueryClient();
  const [commitMessage, setCommitMessage] = useState('');
  const [pushing, setPushing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ commit_url: string; message: string; action: string } | null>(null);
  const [repoInfo, setRepoInfo] = useState<RepoInfo | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setSuccess(null);
    setPushing(false);

    // Pre-fill commit message from playbook metadata
    if (playbook) {
      setCommitMessage(`Update playbook: ${playbook.name} v${playbook.version}`);
    }

    // Load private repo config
    fetch(`${api.getBaseUrl()}/api/playbooks/private-repo`)
      .then(r => r.json())
      .then(setRepoInfo)
      .catch(() => setRepoInfo({ configured: false }));
  }, [open, playbook]);

  const handlePush = async () => {
    if (!playbook) return;
    setPushing(true);
    setError(null);

    try {
      const response = await fetch(`${api.getBaseUrl()}/api/playbooks/private-repo/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook_path: playbook.path,
          commit_message: commitMessage.trim(),
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Push failed');
      }

      const data = await response.json();
      setSuccess({
        commit_url: data.commit_url,
        message: data.message,
        action: data.action,
      });
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPushing(false);
    }
  };

  const targetPath = repoInfo?.folder
    ? `${repoInfo.folder}/${playbook?.path}`
    : playbook?.path;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <GitHubIcon />
        Push to Private Repo
      </DialogTitle>

      <DialogContent>
        {success ? (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <SuccessIcon color="success" sx={{ fontSize: 48, mb: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ textTransform: 'capitalize' }}>
              {success.action}
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              {success.message}
            </Typography>
            <Link href={success.commit_url} target="_blank" rel="noopener noreferrer">
              View commit on GitHub
            </Link>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            {repoInfo && !repoInfo.configured && (
              <Alert severity="warning">
                No private repository configured. Go to{' '}
                <strong>Settings → Integrations</strong> to add your token and repo URL.
              </Alert>
            )}

            {error && <Alert severity="error">{error}</Alert>}

            {/* Playbook summary */}
            {playbook && (
              <Box sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="subtitle2">{playbook.name}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                  {playbook.path} &middot; v{playbook.version} &middot; {playbook.domain}
                </Typography>
                {playbook.description && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    {playbook.description}
                  </Typography>
                )}
              </Box>
            )}

            {/* Repo target */}
            {repoInfo?.configured && (
              <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
                <Typography variant="caption" color="text.secondary">Target:</Typography>
                <Chip label={repoInfo.repo_url} size="small" variant="outlined" />
                <Typography variant="caption" color="text.secondary">→</Typography>
                <Chip label={targetPath} size="small" variant="outlined" sx={{ fontFamily: 'monospace' }} />
              </Box>
            )}

            <TextField
              label="Commit Message"
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              size="small"
              fullWidth
              multiline
              rows={2}
              helperText="Describe what changed in this version of the playbook"
            />
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>{success ? 'Close' : 'Cancel'}</Button>
        {!success && (
          <Button
            variant="contained"
            onClick={handlePush}
            disabled={pushing || !commitMessage.trim() || repoInfo?.configured === false}
            startIcon={pushing ? <CircularProgress size={16} /> : <GitHubIcon />}
          >
            {pushing ? 'Pushing...' : 'Push'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
