/**
 * Settings page with sub-tabs for Credentials, Executions, Updates, and About
 * Styled to match cw-dashboard-dist
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
  Button,
  CircularProgress,
  Alert,
  Chip,
  Link,
  Divider,
  Stack,
  Switch,
  FormControlLabel,
  RadioGroup,
  Radio,
  FormControl,
  TextField,
} from '@mui/material';
import {
  Key as CredentialsIcon,
  Info as AboutIcon,
  Settings as SettingsIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  HelpOutline as UnknownIcon,
  RestartAlt as RestartIcon,
  Palette as AppearanceIcon,
  Brightness4 as DarkModeIcon,
  Brightness7 as LightModeIcon,
  GridView as GridIcon,
  MonitorHeart as DiagnosticsIcon,
  Storage as DataIcon,
  Terminal as LogsIcon,
  GitHub as GitHubIcon,
} from '@mui/icons-material';
import { Credentials } from './Credentials';
import { DiagnosticsSection, DataManagementSection, LogsSection } from '../components/DiagnosticsPanel';
import { api } from '../api/client';
import { useStore } from '../store';
import type { DetailedHealthResponse, HealthStatus } from '../types/api';
import packageJson from '../../package.json';
import { isElectron } from '../utils/platform';
import type { UpdateStatus } from '../types/electron';

function HealthChip({ status, size = 'small' }: { status: HealthStatus | 'unknown'; size?: 'small' | 'medium' }) {
  const config: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'default'; icon: React.ReactElement }> = {
    healthy:   { label: 'Healthy',   color: 'success',  icon: <CheckCircleIcon /> },
    degraded:  { label: 'Degraded',  color: 'warning',  icon: <WarningIcon /> },
    unhealthy: { label: 'Unhealthy', color: 'error',    icon: <ErrorIcon /> },
    unknown:   { label: 'Unknown',   color: 'default',  icon: <UnknownIcon /> },
  };
  const { label, color, icon } = config[status] ?? config.unknown;
  return <Chip label={label} color={color} size={size} icon={icon} />;
}

type SettingsTab = 'credentials' | 'diagnostics' | 'data' | 'logs' | 'integrations' | 'updates' | 'appearance' | 'about';

const settingsTabs: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
  { id: 'credentials', label: 'Gateway Credentials', icon: <CredentialsIcon /> },
  { id: 'diagnostics', label: 'Diagnostics', icon: <DiagnosticsIcon /> },
  { id: 'data', label: 'Data Management', icon: <DataIcon /> },
  { id: 'logs', label: 'Logs', icon: <LogsIcon /> },
  { id: 'integrations', label: 'Integrations', icon: <GitHubIcon /> },
  { id: 'updates', label: 'Updates', icon: <DownloadIcon /> },
  { id: 'appearance', label: 'Appearance', icon: <AppearanceIcon /> },
  { id: 'about', label: 'About', icon: <AboutIcon /> },
];

export function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('credentials');
  const [appVersion, setAppVersion] = useState<string>(packageJson.version);
  const [health, setHealth] = useState<DetailedHealthResponse | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus>({
    checking: false,
    available: false,
    downloading: false,
    downloaded: false,
  });
  const theme = useStore((state) => state.theme);
  const setTheme = useStore((state) => state.setTheme);
  const playbookGridColumns = useStore((state) => state.playbookGridColumns);
  const setPlaybookGridColumns = useStore((state) => state.setPlaybookGridColumns);

  // Public library GitHub token
  const [githubToken, setGithubToken] = useState('');
  const [githubTokenPreview, setGithubTokenPreview] = useState<string | null>(null);
  const [githubTokenConfigured, setGithubTokenConfigured] = useState(false);
  const [githubTokenSaving, setGithubTokenSaving] = useState(false);

  // Private repo state
  const [privateToken, setPrivateToken] = useState('');
  const [privateRepoUrl, setPrivateRepoUrl] = useState('');
  const [privateFolder, setPrivateFolder] = useState('');
  const [privateRepoConfigured, setPrivateRepoConfigured] = useState(false);
  const [privateRepoInfo, setPrivateRepoInfo] = useState<{ repo_url: string; folder: string; token_preview: string } | null>(null);
  const [privateRepoSaving, setPrivateRepoSaving] = useState(false);

  // Remote access state (for MCP/WSL integration)
  const [allowRemoteAccess, setAllowRemoteAccess] = useState(false);

  const loadIntegrationStatus = () => {
    fetch(`${api.getBaseUrl()}/api/playbooks/github-token`)
      .then(r => r.json())
      .then(data => { setGithubTokenConfigured(data.configured); setGithubTokenPreview(data.preview); })
      .catch(() => {});
    fetch(`${api.getBaseUrl()}/api/playbooks/private-repo`)
      .then(r => r.json())
      .then(data => {
        setPrivateRepoConfigured(data.configured);
        if (data.configured) setPrivateRepoInfo({ repo_url: data.repo_url, folder: data.folder, token_preview: data.token_preview });
        else setPrivateRepoInfo(null);
      })
      .catch(() => {});
  };

  // Get app version and health on mount
  useEffect(() => {
    if (isElectron() && window.electronAPI) {
      window.electronAPI.getVersion().then(setAppVersion).catch(() => {});
      window.electronAPI.getSetting('allowRemoteAccess').then((v: unknown) => {
        setAllowRemoteAccess(v === true);
      }).catch(() => {});
    }
    api.diagnostics.getDetailedHealth().then(setHealth).catch(() => {});
    loadIntegrationStatus();
  }, []);

  // Listen for update events from Electron
  useEffect(() => {
    if (!isElectron() || !window.electronAPI) return;

    const unsubscribeProgress = window.electronAPI.on('update:progress', (data) => {
      const status = data as UpdateStatus;
      setUpdateStatus((prev) => ({
        ...prev,
        downloading: true,
        progress: status.progress,
      }));
    });

    const unsubscribeDownloaded = window.electronAPI.on('update:downloaded', (data) => {
      const status = data as UpdateStatus;
      setUpdateStatus((prev) => ({
        ...prev,
        downloading: false,
        downloaded: true,
        progress: 100,
        updateInfo: status.updateInfo || prev.updateInfo,
      }));
    });

    const unsubscribeError = window.electronAPI.on('update:error', (data) => {
      const status = data as UpdateStatus;
      setUpdateStatus((prev) => ({
        ...prev,
        checking: false,
        downloading: false,
        error: status.error,
      }));
    });

    const unsubscribeAvailable = window.electronAPI.on('update:available', (data) => {
      const status = data as UpdateStatus;
      setUpdateStatus((prev) => ({
        ...prev,
        checking: false,
        available: true,
        updateInfo: status.updateInfo,
      }));
    });

    const unsubscribeNotAvailable = window.electronAPI.on('update:not-available', () => {
      setUpdateStatus((prev) => ({
        ...prev,
        checking: false,
        available: false,
      }));
    });

    return () => {
      unsubscribeProgress();
      unsubscribeDownloaded();
      unsubscribeError();
      unsubscribeAvailable();
      unsubscribeNotAvailable();
    };
  }, []);

  const handleCheckUpdate = async () => {
    if (!isElectron() || !window.electronAPI) return;
    setUpdateStatus((prev) => ({ ...prev, checking: true, error: undefined }));
    try {
      const result = await window.electronAPI.checkForUpdates();
      setUpdateStatus(result);
    } catch (err) {
      setUpdateStatus((prev) => ({
        ...prev,
        checking: false,
        error: err instanceof Error ? err.message : 'Failed to check for updates',
      }));
    }
  };

  const handleDownloadUpdate = async () => {
    if (!isElectron() || !window.electronAPI) return;
    setUpdateStatus((prev) => ({ ...prev, downloading: true, error: undefined }));
    try {
      await window.electronAPI.downloadUpdate();
      // The status will be updated via events, but set downloading for UI feedback
    } catch (err) {
      setUpdateStatus((prev) => ({
        ...prev,
        downloading: false,
        error: err instanceof Error ? err.message : 'Failed to download update',
      }));
    }
  };

  const handleInstallUpdate = async () => {
    if (!isElectron() || !window.electronAPI) return;
    try {
      await window.electronAPI.installUpdate();
    } catch (err) {
      setUpdateStatus((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to install update',
      }));
    }
  };

  const handleSaveGithubToken = async () => {
    if (!githubToken.trim()) return;
    setGithubTokenSaving(true);
    try {
      await fetch(`${api.getBaseUrl()}/api/playbooks/github-token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: githubToken.trim() }),
      });
      setGithubTokenConfigured(true);
      setGithubTokenPreview(`${githubToken.trim().slice(0, 4)}...${githubToken.trim().slice(-4)}`);
      setGithubToken('');
    } catch {
      // Error handled silently
    } finally {
      setGithubTokenSaving(false);
    }
  };

  const handleClearGithubToken = async () => {
    try {
      await fetch(`${api.getBaseUrl()}/api/playbooks/github-token`, { method: 'DELETE' });
      setGithubTokenConfigured(false);
      setGithubTokenPreview(null);
    } catch {
      // Error handled silently
    }
  };

  const handleSavePrivateRepo = async () => {
    if (!privateToken.trim() || !privateRepoUrl.trim()) return;
    setPrivateRepoSaving(true);
    try {
      await fetch(`${api.getBaseUrl()}/api/playbooks/private-repo`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: privateToken.trim(), repo_url: privateRepoUrl.trim(), folder: privateFolder.trim() }),
      });
      setPrivateToken('');
      setPrivateRepoUrl('');
      setPrivateFolder('');
      loadIntegrationStatus();
    } catch {
      // Error handled silently
    } finally {
      setPrivateRepoSaving(false);
    }
  };

  const handleClearPrivateRepo = async () => {
    try {
      await fetch(`${api.getBaseUrl()}/api/playbooks/private-repo`, { method: 'DELETE' });
      setPrivateRepoConfigured(false);
      setPrivateRepoInfo(null);
    } catch {
      // Error handled silently
    }
  };

  const renderIntegrationsContent = () => (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Typography variant="h6" sx={{ mb: 3 }}>
        Integrations
      </Typography>

      <Stack spacing={3}>
        <Paper
          sx={{
            p: 3,
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5, textTransform: 'uppercase', letterSpacing: 1 }}>
            GitHub — Submit to Public Library
          </Typography>
          <Link
            href="https://github.com/Gaskony-Ignition/ignition-toolbox"
            target="_blank"
            rel="noopener noreferrer"
            variant="caption"
            sx={{ mb: 2, display: 'block' }}
          >
            github.com/Gaskony-Ignition/ignition-toolbox
          </Link>
          <Divider sx={{ mb: 3 }} />

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            A GitHub Personal Access Token (PAT) with <strong>repo</strong> scope is required to submit playbooks to the public library repository.
          </Typography>

          {githubTokenConfigured ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Chip
                label={`Token: ${githubTokenPreview || '****'}`}
                color="success"
                variant="outlined"
              />
              <Button
                variant="outlined"
                color="error"
                size="small"
                onClick={handleClearGithubToken}
              >
                Remove Token
              </Button>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
              <TextField
                label="GitHub Personal Access Token"
                value={githubToken}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setGithubToken(e.target.value)}
                type="password"
                size="small"
                fullWidth
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              />
              <Button
                variant="contained"
                onClick={handleSaveGithubToken}
                disabled={!githubToken.trim() || githubTokenSaving}
                sx={{ minWidth: 80 }}
              >
                {githubTokenSaving ? 'Saving...' : 'Save'}
              </Button>
            </Box>
          )}
        </Paper>

        {/* Private Repository */}
        <Paper sx={{ p: 3, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider' }}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
            GitHub — Private Repository
          </Typography>
          <Divider sx={{ mb: 3 }} />

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Connect a private GitHub repository to version your playbooks. A PAT with <strong>repo</strong> scope is required.
            Playbooks are committed directly to the repository whenever you choose to push them.
          </Typography>

          {privateRepoConfigured && privateRepoInfo ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Chip label={`Token: ${privateRepoInfo.token_preview}`} color="success" variant="outlined" size="small" />
                <Chip label={privateRepoInfo.repo_url} variant="outlined" size="small" />
                {privateRepoInfo.folder && (
                  <Chip label={`Folder: ${privateRepoInfo.folder}`} variant="outlined" size="small" />
                )}
              </Box>
              <Box>
                <Button variant="outlined" color="error" size="small" onClick={handleClearPrivateRepo}>
                  Remove
                </Button>
              </Box>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              <TextField
                label="GitHub Personal Access Token"
                value={privateToken}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPrivateToken(e.target.value)}
                type="password"
                size="small"
                fullWidth
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              />
              <TextField
                label="Repository URL"
                value={privateRepoUrl}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPrivateRepoUrl(e.target.value)}
                size="small"
                fullWidth
                placeholder="https://github.com/username/my-playbooks"
                helperText="Supports https://github.com/... or username/repo formats"
              />
              <TextField
                label="Folder (optional)"
                value={privateFolder}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPrivateFolder(e.target.value)}
                size="small"
                fullWidth
                placeholder="playbooks"
                helperText="Sub-folder within the repo to store playbooks. Leave blank for root."
              />
              <Box>
                <Button
                  variant="contained"
                  onClick={handleSavePrivateRepo}
                  disabled={!privateToken.trim() || !privateRepoUrl.trim() || privateRepoSaving}
                >
                  {privateRepoSaving ? 'Saving...' : 'Save'}
                </Button>
              </Box>
            </Box>
          )}
        </Paper>

        {/* MCP / Remote Access */}
        {isElectron() && (
          <Paper
            sx={{
              p: 3,
              bgcolor: 'background.paper',
              border: '1px solid',
              borderColor: 'divider',
            }}
          >
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
              MCP / Remote Access
            </Typography>
            <Divider sx={{ mb: 3 }} />

            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box>
                <Typography variant="body1" fontWeight="medium">
                  Allow Remote Access
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Bind backend to all network interfaces (0.0.0.0) so WSL, MCP servers, and other local tools can reach it. Requires restart.
                </Typography>
              </Box>
              <FormControlLabel
                control={
                  <Switch
                    checked={allowRemoteAccess}
                    onChange={async (e) => {
                      const newValue = e.target.checked;
                      setAllowRemoteAccess(newValue);
                      if (window.electronAPI) {
                        await window.electronAPI.setSetting('allowRemoteAccess', newValue);
                      }
                    }}
                    color="primary"
                  />
                }
                label=""
              />
            </Box>
            {allowRemoteAccess && (
              <Alert severity="success" sx={{ mt: 2 }}>
                Remote access is active. The backend is bound to 0.0.0.0 and accessible from WSL, MCP servers, and other local tools.
              </Alert>
            )}
          </Paper>
        )}
      </Stack>
    </Box>
  );

  const renderUpdatesContent = () => (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Typography variant="h6" sx={{ mb: 3 }}>
        Software Updates
      </Typography>

      {!isElectron() ? (
        <Paper
          sx={{
            p: 4,
            textAlign: 'center',
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <ErrorIcon sx={{ fontSize: 48, color: 'warning.main', mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            Desktop Only Feature
          </Typography>
          <Typography color="text.secondary">
            Auto-updates are only available in the desktop application.
          </Typography>
        </Paper>
      ) : (
        <Paper
          sx={{
            p: 3,
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Stack spacing={3}>
            {/* Current Version */}
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Current Version
                </Typography>
                <Typography variant="h5" fontWeight="bold">
                  v{appVersion}
                </Typography>
              </Box>
              <Button
                variant="outlined"
                startIcon={updateStatus.checking ? <CircularProgress size={16} /> : <RefreshIcon />}
                onClick={handleCheckUpdate}
                disabled={updateStatus.checking || updateStatus.downloading}
              >
                {updateStatus.checking ? 'Checking...' : 'Check for Updates'}
              </Button>
            </Box>

            {/* Update Available */}
            {updateStatus.available && !updateStatus.downloaded && (
              <Paper
                sx={{
                  p: 2,
                  bgcolor: 'primary.main',
                  color: 'primary.contrastText',
                  backgroundImage: 'linear-gradient(rgba(255,255,255,0.1), rgba(255,255,255,0))',
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography variant="subtitle1" fontWeight="medium" gutterBottom>
                      Update Available: v{updateStatus.updateInfo?.version}
                    </Typography>
                    {updateStatus.updateInfo?.releaseNotes && (
                      <Typography variant="body2" sx={{ opacity: 0.9, whiteSpace: 'pre-line' }}>
                        {updateStatus.updateInfo.releaseNotes.replace(/<[^>]+>/g, '')}
                      </Typography>
                    )}
                  </Box>
                  <Button
                    variant="contained"
                    color="inherit"
                    startIcon={updateStatus.downloading ? <CircularProgress size={16} /> : <DownloadIcon />}
                    onClick={handleDownloadUpdate}
                    disabled={updateStatus.downloading}
                    sx={{ bgcolor: 'white', color: 'primary.main', '&:hover': { bgcolor: 'grey.100' } }}
                  >
                    {updateStatus.downloading ? 'Downloading...' : 'Download'}
                  </Button>
                </Box>
                {updateStatus.downloading && updateStatus.progress !== undefined && (
                  <Box sx={{ mt: 2 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="caption">Downloading...</Typography>
                      <Typography variant="caption">{Math.round(updateStatus.progress)}%</Typography>
                    </Box>
                    <Box
                      sx={{
                        height: 4,
                        bgcolor: 'rgba(255,255,255,0.3)',
                        borderRadius: 2,
                        overflow: 'hidden',
                      }}
                    >
                      <Box
                        sx={{
                          height: '100%',
                          width: `${updateStatus.progress}%`,
                          bgcolor: 'white',
                          borderRadius: 2,
                          transition: 'width 0.3s',
                        }}
                      />
                    </Box>
                  </Box>
                )}
              </Paper>
            )}

            {/* Update Downloaded */}
            {updateStatus.downloaded && (
              <Paper
                sx={{
                  p: 2,
                  bgcolor: 'success.main',
                  color: 'success.contrastText',
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <CheckCircleIcon />
                    <Box>
                      <Typography variant="subtitle1" fontWeight="medium">
                        Update Ready to Install
                      </Typography>
                      <Typography variant="body2" sx={{ opacity: 0.9 }}>
                        Restart the application to install v{updateStatus.updateInfo?.version}
                      </Typography>
                    </Box>
                  </Box>
                  <Button
                    variant="contained"
                    color="inherit"
                    startIcon={<RestartIcon />}
                    onClick={handleInstallUpdate}
                    sx={{ bgcolor: 'white', color: 'success.main', '&:hover': { bgcolor: 'grey.100' } }}
                  >
                    Restart & Install
                  </Button>
                </Box>
              </Paper>
            )}

            {/* No Update Available Message */}
            {!updateStatus.available && !updateStatus.checking && !updateStatus.error && (
              <Alert severity="success" icon={<CheckCircleIcon />}>
                You are running the latest version.
              </Alert>
            )}

            {/* Error */}
            {updateStatus.error && (
              <Alert severity="error">
                {updateStatus.error}
              </Alert>
            )}

            {/* Update Settings */}
            <Divider />
            <Box>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
                Update Settings
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Updates are manual only. Check for updates when you want, download when ready, and install when convenient.
              </Typography>
            </Box>
          </Stack>
        </Paper>
      )}
    </Box>
  );

  const renderAboutContent = () => (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Typography variant="h6" sx={{ mb: 3 }}>
        About Ignition Toolbox
      </Typography>

      <Stack spacing={3}>
        {/* App Info Card */}
        <Paper
          sx={{
            p: 4,
            textAlign: 'center',
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Box
            sx={{
              width: 64,
              height: 64,
              bgcolor: 'primary.main',
              borderRadius: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              mx: 'auto',
              mb: 2,
            }}
          >
            <SettingsIcon sx={{ fontSize: 32, color: 'white' }} />
          </Box>
          <Typography variant="h5" fontWeight="bold" gutterBottom>
            Ignition Toolbox
          </Typography>
          <Typography color="text.secondary" gutterBottom>
            Version {appVersion}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 400, mx: 'auto', mt: 2 }}>
            Visual acceptance testing platform for Ignition SCADA systems.
            Automate Gateway, Designer, and Perspective operations with playbook-driven workflows.
          </Typography>
        </Paper>

        {/* System Information */}
        <Paper
          sx={{
            p: 3,
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
            System Information
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Stack spacing={2}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Platform</Typography>
              <Typography variant="body2">
                {isElectron() ? 'Desktop (Electron)' : 'Web Browser'}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Frontend Version</Typography>
              <Typography variant="body2">{packageJson.version}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Backend Version</Typography>
              <Typography variant="body2">{health?.status ? (health as any).version || '—' : 'Loading...'}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2" color="text.secondary">Backend Status</Typography>
              <HealthChip status={health?.status ?? 'unknown'} />
            </Box>
            {/* Per-component breakdown — only shown when not fully healthy */}
            {health?.components && (
              <Box sx={{ pl: 2, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                {(Object.entries(health.components) as [string, { status: HealthStatus; message: string; error?: string }][]).map(
                  ([name, comp]) => (
                    <Box key={name} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1 }}>
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'capitalize' }}>
                          {name}
                        </Typography>
                        {(comp.status === 'unhealthy' || comp.status === 'degraded') && (comp.error || comp.message) && (
                          <Typography variant="caption" display="block" color={comp.status === 'unhealthy' ? 'error.main' : 'warning.main'} sx={{ fontSize: '0.68rem' }}>
                            {comp.error || comp.message}
                          </Typography>
                        )}
                      </Box>
                      <HealthChip status={comp.status} size="small" />
                    </Box>
                  )
                )}
              </Box>
            )}
            {/* System-level errors and warnings */}
            {health?.errors && health.errors.length > 0 && (
              <Alert severity="error" sx={{ py: 0.5 }}>
                {health.errors.map((e, i) => <div key={i}>{e}</div>)}
              </Alert>
            )}
            {health?.warnings && health.warnings.length > 0 && (
              <Alert severity="warning" sx={{ py: 0.5 }}>
                {health.warnings.map((w, i) => <div key={i}>{w}</div>)}
              </Alert>
            )}
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">License</Typography>
              <Typography variant="body2">MIT License</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Repository</Typography>
              <Link
                href="https://github.com/Gaskony-Ignition/ignition-toolbox"
                target="_blank"
                rel="noopener noreferrer"
                sx={{ fontSize: '0.875rem' }}
              >
                github.com/Gaskony-Ignition/ignition-toolbox
              </Link>
            </Box>
          </Stack>
        </Paper>
      </Stack>
    </Box>
  );

  const renderAppearanceContent = () => (
    <Box sx={{ width: '100%', maxWidth: '100%' }}>
      <Typography variant="h6" sx={{ mb: 3 }}>
        Appearance
      </Typography>

      <Stack spacing={3}>
        {/* Theme Section */}
        <Paper
          sx={{
            p: 3,
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
            Theme
          </Typography>
          <Divider sx={{ mb: 3 }} />

          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              {theme === 'dark' ? (
                <DarkModeIcon sx={{ color: 'primary.main' }} />
              ) : (
                <LightModeIcon sx={{ color: 'warning.main' }} />
              )}
              <Box>
                <Typography variant="body1" fontWeight="medium">
                  {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {theme === 'dark'
                    ? 'Using dark theme with navy blue background'
                    : 'Using light theme with white background'}
                </Typography>
              </Box>
            </Box>
            <FormControlLabel
              control={
                <Switch
                  checked={theme === 'dark'}
                  onChange={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                  color="primary"
                />
              }
              label=""
            />
          </Box>
        </Paper>

        {/* Playbook Grid Columns Section */}
        <Paper
          sx={{
            p: 3,
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: 'uppercase', letterSpacing: 1 }}>
            Playbook Grid
          </Typography>
          <Divider sx={{ mb: 3 }} />

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
            <GridIcon sx={{ color: 'primary.main' }} />
            <Box>
              <Typography variant="body1" fontWeight="medium">
                Maximum Columns
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Maximum number of playbook cards per row on large screens
              </Typography>
            </Box>
          </Box>

          <FormControl component="fieldset">
            <RadioGroup
              row
              value={playbookGridColumns}
              onChange={(e) => setPlaybookGridColumns(parseInt(e.target.value, 10) as 3 | 4 | 5 | 6)}
            >
              {[3, 4, 5, 6].map((cols) => (
                <FormControlLabel
                  key={cols}
                  value={cols}
                  control={<Radio size="small" />}
                  label={
                    <Typography
                      variant="body2"
                      fontWeight={playbookGridColumns === cols ? 'medium' : 'normal'}
                    >
                      {cols}
                    </Typography>
                  }
                  sx={{ mr: 3 }}
                />
              ))}
            </RadioGroup>
          </FormControl>
        </Paper>
      </Stack>
    </Box>
  );

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3, flexShrink: 0 }}>
        <SettingsIcon sx={{ color: 'primary.main' }} />
        <Typography variant="h5" fontWeight="bold">
          Settings
        </Typography>
      </Box>

      <Box sx={{ display: 'flex', gap: 3, flex: 1 }}>
        {/* Sidebar */}
        <Paper
          elevation={0}
          sx={{
            width: 240,
            flexShrink: 0,
            bgcolor: 'background.paper',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 2,
            alignSelf: 'flex-start',
          }}
        >
          <List sx={{ p: 1 }}>
            {settingsTabs.map((tab) => (
              <ListItemButton
                key={tab.id}
                selected={activeTab === tab.id}
                onClick={() => setActiveTab(tab.id)}
                sx={{
                  borderRadius: 1,
                  mb: 0.5,
                  '&.Mui-selected': {
                    bgcolor: 'rgba(59, 130, 246, 0.15)',
                    color: 'primary.main',
                    '&:hover': {
                      bgcolor: 'rgba(59, 130, 246, 0.25)',
                    },
                    '& .MuiListItemIcon-root': {
                      color: 'primary.main',
                    },
                  },
                  '&:hover': {
                    bgcolor: 'action.hover',
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 36, color: activeTab === tab.id ? 'primary.main' : 'text.secondary' }}>
                  {tab.icon}
                </ListItemIcon>
                <ListItemText
                  primary={tab.label}
                  primaryTypographyProps={{
                    fontSize: '0.875rem',
                    fontWeight: activeTab === tab.id ? 600 : 400,
                  }}
                />
              </ListItemButton>
            ))}
          </List>
        </Paper>

        {/* Content - fills remaining width */}
        <Box
          sx={{
            flex: 1,
            minWidth: 0,
            overflow: 'auto',
          }}
        >
          {activeTab === 'credentials' && <Credentials />}
          {activeTab === 'diagnostics' && <DiagnosticsSection />}
          {activeTab === 'data' && <DataManagementSection />}
          {activeTab === 'logs' && <LogsSection />}
          {activeTab === 'integrations' && renderIntegrationsContent()}
          {activeTab === 'updates' && renderUpdatesContent()}
          {activeTab === 'appearance' && renderAppearanceContent()}
          {activeTab === 'about' && renderAboutContent()}
        </Box>
      </Box>
    </Box>
  );
}
