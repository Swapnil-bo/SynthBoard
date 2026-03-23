import { useCallback, useEffect, useState } from 'react'
import api from '../../lib/api'

const RANK_OPTIONS = [8, 16, 32, 64]
const ALPHA_OPTIONS = [16, 32, 64, 128]
const SEQ_LEN_OPTIONS = [256, 512, 1024, 2048]

const TOOLTIPS = {
  model: 'Base model to fine-tune. Tier 1 models are recommended for 6GB VRAM. Tier 2 models are tight — monitor VRAM closely.',
  dataset: 'Select a formatted dataset. Unformatted datasets must be formatted on the Datasets page first.',
  r: 'LoRA rank — controls adapter capacity. Higher = more expressive but more VRAM. 16 is the sweet spot for small models.',
  lora_alpha: 'LoRA scaling factor. Convention: alpha = 2 * rank. Higher values give LoRA updates more influence.',
  epochs: 'Number of full passes over the dataset. 3 is a good default. More epochs risk overfitting on small datasets.',
  lr: 'Learning rate. 2e-4 is standard for QLoRA. Lower (1e-4) for larger models or fine-grained tasks.',
  max_seq_length: 'Maximum token length per sample. Longer = more VRAM. 1024 is safe for 6GB. 2048 is risky.',
  max_steps: 'Override total training steps. Leave empty to train for the full number of epochs.',
}

export default function TrainingConfig({ onTrainingStarted }) {
  // Data sources
  const [capabilities, setCapabilities] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [loadingCaps, setLoadingCaps] = useState(true)
  const [loadingDatasets, setLoadingDatasets] = useState(true)

  // Form state
  const [modelName, setModelName] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [r, setR] = useState(16)
  const [loraAlpha, setLoraAlpha] = useState(32)
  const [epochs, setEpochs] = useState(3)
  const [lr, setLr] = useState('2e-4')
  const [maxSeqLength, setMaxSeqLength] = useState(1024)
  const [maxSteps, setMaxSteps] = useState('')

  // Submission state
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Fetch capabilities
  const fetchCapabilities = useCallback(async () => {
    try {
      const { data } = await api.get('/system/capabilities')
      setCapabilities(data)
      // Auto-select first tier 1 model
      const tier1 = data.available_model_tiers?.find(m => m.tier === 1)
      if (tier1 && !modelName) setModelName(tier1.model_id)
    } catch {
      // ignore
    } finally {
      setLoadingCaps(false)
    }
  }, [])

  // Fetch datasets (only formatted ones are usable)
  const fetchDatasets = useCallback(async () => {
    try {
      const { data } = await api.get('/datasets')
      setDatasets(data.datasets || [])
      // Auto-select first formatted dataset
      const formatted = (data.datasets || []).find(d => d.formatted_path)
      if (formatted && !datasetId) setDatasetId(formatted.id)
    } catch {
      // ignore
    } finally {
      setLoadingDatasets(false)
    }
  }, [])

  useEffect(() => { fetchCapabilities() }, [fetchCapabilities])
  useEffect(() => { fetchDatasets() }, [fetchDatasets])

  // Derived
  const selectedModel = capabilities?.available_model_tiers?.find(m => m.model_id === modelName)
  const formattedDatasets = datasets.filter(d => d.formatted_path)
  const loading = loadingCaps || loadingDatasets

  const handleSubmit = async () => {
    setError(null)

    if (!modelName) { setError('Select a model.'); return }
    if (!datasetId) { setError('Select a dataset.'); return }

    const parsedLr = parseFloat(lr)
    if (isNaN(parsedLr) || parsedLr <= 0) { setError('Learning rate must be a positive number.'); return }

    const parsedMaxSteps = maxSteps === '' ? 0 : parseInt(maxSteps, 10)
    if (maxSteps !== '' && (isNaN(parsedMaxSteps) || parsedMaxSteps < 1)) {
      setError('Max steps must be a positive integer or empty.')
      return
    }

    setSubmitting(true)
    try {
      const { data } = await api.post('/training/start', {
        model_name: modelName,
        dataset_id: datasetId,
        r,
        lora_alpha: loraAlpha,
        num_train_epochs: epochs,
        learning_rate: parsedLr,
        max_seq_length: maxSeqLength,
        max_steps: parsedMaxSteps,
      })
      onTrainingStarted?.(data)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message || 'Failed to start training.'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="p-5">
        <div className="text-sm text-text-muted">Loading configuration...</div>
      </div>
    )
  }

  const trainingReady = capabilities?.training_ready

  return (
    <div className="p-5 space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Training Configuration</h2>
        <p className="text-xs text-text-muted mt-1">Configure QLoRA fine-tuning parameters</p>
      </div>

      {!trainingReady && (
        <div className="bg-accent-error/10 border border-accent-error/30 rounded-lg px-4 py-3">
          <div className="text-sm text-accent-error font-medium">Training Not Ready</div>
          <div className="text-xs text-text-secondary mt-1">
            Missing dependencies: {capabilities?.warnings?.join(', ') || 'unknown'}
          </div>
        </div>
      )}

      {/* Model Selection */}
      <FieldGroup label="Base Model" tooltip={TOOLTIPS.model}>
        <select
          value={modelName}
          onChange={e => setModelName(e.target.value)}
          className="w-full bg-bg-primary border border-border-default rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent-info"
        >
          <option value="">Select a model...</option>
          {capabilities?.available_model_tiers?.map(m => (
            <option key={m.model_id} value={m.model_id}>
              {formatModelLabel(m)}
            </option>
          ))}
        </select>
        {selectedModel && (
          <ModelBadges model={selectedModel} />
        )}
      </FieldGroup>

      {/* Dataset Selection */}
      <FieldGroup label="Dataset" tooltip={TOOLTIPS.dataset}>
        <select
          value={datasetId}
          onChange={e => setDatasetId(e.target.value)}
          className="w-full bg-bg-primary border border-border-default rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent-info"
        >
          <option value="">Select a dataset...</option>
          {formattedDatasets.map(d => (
            <option key={d.id} value={d.id}>
              {d.original_filename} ({d.num_samples} samples, ~{d.avg_token_length} tok)
            </option>
          ))}
        </select>
        {datasets.length > 0 && formattedDatasets.length === 0 && (
          <div className="text-xs text-accent-warning mt-1">
            No formatted datasets. Format a dataset on the Datasets page first.
          </div>
        )}
        {datasets.length === 0 && (
          <div className="text-xs text-accent-warning mt-1">
            No datasets uploaded yet. Upload one on the Datasets page.
          </div>
        )}
      </FieldGroup>

      {/* Hyperparameters */}
      <div className="border-t border-border-subtle pt-4">
        <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-3">
          LoRA Parameters
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <DiscreteSlider
            label="LoRA Rank (r)"
            tooltip={TOOLTIPS.r}
            options={RANK_OPTIONS}
            value={r}
            onChange={setR}
          />
          <DiscreteSlider
            label="LoRA Alpha"
            tooltip={TOOLTIPS.lora_alpha}
            options={ALPHA_OPTIONS}
            value={loraAlpha}
            onChange={setLoraAlpha}
          />
        </div>
      </div>

      <div className="border-t border-border-subtle pt-4">
        <h3 className="text-xs font-medium text-text-muted uppercase tracking-wide mb-3">
          Training Parameters
        </h3>
        <div className="grid grid-cols-2 gap-4">
          <RangeSlider
            label="Epochs"
            tooltip={TOOLTIPS.epochs}
            min={1}
            max={10}
            value={epochs}
            onChange={setEpochs}
          />
          <TextInput
            label="Learning Rate"
            tooltip={TOOLTIPS.lr}
            value={lr}
            onChange={setLr}
            placeholder="2e-4"
            mono
          />
          <DiscreteSlider
            label="Max Seq Length"
            tooltip={TOOLTIPS.max_seq_length}
            options={SEQ_LEN_OPTIONS}
            value={maxSeqLength}
            onChange={setMaxSeqLength}
            warn={maxSeqLength > 1024}
            warnText="High VRAM usage"
          />
          <TextInput
            label="Max Steps (optional)"
            tooltip={TOOLTIPS.max_steps}
            value={maxSteps}
            onChange={setMaxSteps}
            placeholder="Leave empty for full epochs"
          />
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="bg-accent-error/10 border border-accent-error/30 rounded-lg px-4 py-3">
          <div className="text-sm text-accent-error">{error}</div>
        </div>
      )}

      {/* Submit button */}
      <button
        onClick={handleSubmit}
        disabled={submitting || !trainingReady || !modelName || !datasetId}
        className="w-full py-2.5 rounded-lg font-medium text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed bg-accent-success/20 text-accent-success border border-accent-success/30 hover:bg-accent-success/30"
      >
        {submitting ? 'Starting Training...' : 'Start Training'}
      </button>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FieldGroup({ label, tooltip, children }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1.5">
        <label className="text-sm font-medium text-text-secondary">{label}</label>
        {tooltip && <Tooltip text={tooltip} />}
      </div>
      {children}
    </div>
  )
}

function Tooltip({ text }) {
  const [show, setShow] = useState(false)
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className="cursor-help text-text-muted text-xs w-4 h-4 flex items-center justify-center rounded-full border border-border-default hover:border-text-muted transition-colors">
        ?
      </span>
      {show && (
        <span className="absolute z-50 left-6 top-0 w-64 bg-bg-surface border border-border-default rounded-md px-3 py-2 text-xs text-text-secondary shadow-lg">
          {text}
        </span>
      )}
    </span>
  )
}

function ModelBadges({ model }) {
  return (
    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
        model.tier === 1
          ? 'bg-accent-success/15 text-accent-success'
          : 'bg-accent-warning/15 text-accent-warning'
      }`}>
        Tier {model.tier}
      </span>
      <span className="text-xs text-text-muted font-mono">{model.params}</span>
      <span className="text-xs text-text-muted">~{model.vram_train_mb} MB VRAM</span>
      {model.gated && (
        <span className="text-xs px-1.5 py-0.5 rounded bg-accent-info/15 text-accent-info font-medium">
          Gated
        </span>
      )}
      {model.tier === 2 && (
        <span className="text-xs text-accent-warning">
          VRAM tight — monitor closely
        </span>
      )}
    </div>
  )
}

function DiscreteSlider({ label, tooltip, options, value, onChange, warn, warnText }) {
  const idx = options.indexOf(value)
  const pos = idx >= 0 ? idx : 0

  return (
    <FieldGroup label={label} tooltip={tooltip}>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={options.length - 1}
          step={1}
          value={pos}
          onChange={e => onChange(options[parseInt(e.target.value)])}
          className="flex-1 accent-accent-info h-1.5"
        />
        <span className={`font-mono text-sm w-12 text-right ${
          warn ? 'text-accent-warning' : 'text-text-primary'
        }`}>
          {value}
        </span>
      </div>
      {warn && warnText && (
        <div className="text-xs text-accent-warning mt-0.5">{warnText}</div>
      )}
    </FieldGroup>
  )
}

function RangeSlider({ label, tooltip, min, max, value, onChange }) {
  return (
    <FieldGroup label={label} tooltip={tooltip}>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={1}
          value={value}
          onChange={e => onChange(parseInt(e.target.value))}
          className="flex-1 accent-accent-info h-1.5"
        />
        <span className="font-mono text-sm text-text-primary w-12 text-right">
          {value}
        </span>
      </div>
    </FieldGroup>
  )
}

function TextInput({ label, tooltip, value, onChange, placeholder, mono }) {
  return (
    <FieldGroup label={label} tooltip={tooltip}>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full bg-bg-primary border border-border-default rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-info ${
          mono ? 'font-mono' : ''
        }`}
      />
    </FieldGroup>
  )
}

function formatModelLabel(m) {
  // e.g. "unsloth/Qwen2.5-1.5B-bnb-4bit" → "Qwen2.5-1.5B-bnb-4bit"
  const shortName = m.model_id.split('/').pop()
  const tierLabel = m.tier === 1 ? '[T1]' : '[T2]'
  const gatedLabel = m.gated ? ' (gated)' : ''
  return `${tierLabel} ${shortName} — ${m.params}, ~${m.vram_train_mb}MB${gatedLabel}`
}
