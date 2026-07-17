import { useEffect, useState } from 'react';
import { rpgWorldBundleClient } from '../../api/rpgWorldBundleClient';

interface RpgWorldBundleTransferProps {
  initialWorldId?: string;
  onImported?: (worldId: string) => Promise<void> | void;
}

export function RpgWorldBundleTransfer({
  initialWorldId = '',
  onImported,
}: RpgWorldBundleTransferProps) {
  const [exportWorldId, setExportWorldId] = useState(initialWorldId);
  const [importFile, setImportFile] = useState<File>();
  const [targetWorldId, setTargetWorldId] = useState('');
  const [feedback, setFeedback] = useState<string>();
  const [error, setError] = useState<string>();
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    if (initialWorldId) setExportWorldId(initialWorldId);
  }, [initialWorldId]);

  const exportWorld = async () => {
    const worldId = exportWorldId.trim();
    if (!worldId || exporting) return;
    setExporting(true);
    try {
      const download = await rpgWorldBundleClient.exportWorld(worldId);
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = download.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setFeedback(`World bundle exported: ${download.filename}`);
      setError(undefined);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'World export failed.');
    } finally {
      setExporting(false);
    }
  };

  const importWorld = async () => {
    if (!importFile || importing) return;
    setImporting(true);
    try {
      const result = await rpgWorldBundleClient.importWorld(importFile, targetWorldId);
      const imageCount = (result.counts.images_created ?? 0) + (result.counts.images_reused ?? 0);
      setFeedback(
        `World imported: ${result.world_id} • ${result.counts.map_definitions ?? 0} maps • ${imageCount} images`,
      );
      setError(undefined);
      setExportWorldId(result.world_id);
      setImportFile(undefined);
      setTargetWorldId('');
      await onImported?.(result.world_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'World import failed.');
    } finally {
      setImporting(false);
    }
  };

  return (
    <section className="rpg-world-library-panel rpg-world-library-form" aria-label="World export and import">
      <p className="eyebrow">Portable bundle</p>
      <h3>Export / import world</h3>
      <p>
        Transfer world canon, topic history, scenarios, map blueprints, compiled maps,
        releases, and referenced images in one checksummed archive.
      </p>
      <label>
        <span>World id to export</span>
        <input
          value={exportWorldId}
          placeholder="world:my-world"
          onChange={(event) => setExportWorldId(event.currentTarget.value)}
        />
      </label>
      <button
        type="button"
        className="rpg-secondary-button"
        disabled={!exportWorldId.trim() || exporting}
        onClick={() => void exportWorld()}
      >
        {exporting ? 'Preparing export…' : 'Export world bundle'}
      </button>
      <label>
        <span>World bundle</span>
        <input
          aria-label="World bundle file"
          type="file"
          accept=".zip,.omnix-world.zip,application/zip"
          onChange={(event) => setImportFile(event.currentTarget.files?.[0])}
        />
      </label>
      <label>
        <span>New world id (optional)</span>
        <input
          value={targetWorldId}
          placeholder="Use bundle world id"
          onChange={(event) => setTargetWorldId(event.currentTarget.value)}
        />
      </label>
      <button
        type="button"
        disabled={!importFile || importing}
        onClick={() => void importWorld()}
      >
        {importing ? 'Validating and importing…' : 'Import world bundle'}
      </button>
      <small>Imports never overwrite an existing world. Use a new world id to create a portable clone.</small>
      {feedback ? <p className="rpg-world-library-feedback" aria-live="polite">{feedback}</p> : null}
      {error ? <p className="rpg-world-library-error" aria-live="assertive">{error}</p> : null}
    </section>
  );
}
