// ---------------------------------------------------------------------------
// Paper
// ---------------------------------------------------------------------------

export interface Paper {
  id: string;
  // Backend emits lowercase enum values
  source: 'pdf_upload' | 'arxiv_url' | 'doi';
  source_url: string | null;
  pdf_storage_path: string | null;
  metadata: PaperMetadata | null;
  created_at: string;
  updated_at: string;
}

export interface PaperMetadata {
  title: string;
  authors: string[];
  abstract: string | null;
  venue: string | null;
  year: number | null;
  arxiv_id: string | null;
  doi: string | null;
  page_count: number | null;
  domain: string | null;
  sub_domain: string | null;
}

// ---------------------------------------------------------------------------
// Pipeline Run
// ---------------------------------------------------------------------------

export interface PipelineRun {
  id: string;
  paper_id: string;
  // Backend emits lowercase enum values
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial';
  stages: Record<string, StageResult>;
  started_at: string | null;
  completed_at: string | null;
  total_tokens: number | null;
  error: string | null;
  created_at: string;
}

export interface StageResult {
  stage_name: string;
  // Backend emits lowercase enum values
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'cached';
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  cached: boolean;
  token_count: number | null;
}

// ---------------------------------------------------------------------------
// Output Bundle
// ---------------------------------------------------------------------------

export interface OutputBundle {
  paper_id: string;
  summaries: SummaryOutput[];
  diagrams: DiagramOutput[];
  code: CodeOutput | null;
  report: ReportOutput | null;
  extraction: ExtractionData | null;
}

export interface SummaryOutput {
  paper_id: string;
  level: 'paragraph' | 'section_by_section' | 'bullets' | 'eli5';
  content: string;
  created_at?: string;
}

export interface DiagramOutput {
  paper_id: string;
  diagram_type: 'architecture' | 'training_flow' | 'inference_flow';
  dsl_code: string;
  svg_path: string | null;
  dsl_language?: string;
  created_at?: string;
}

export interface CodeOutput {
  paper_id: string;
  python_path: string | null;
  notebook_path: string | null;
  synthetic_data_description: string | null;
  created_at?: string;
}

export interface ReportOutput {
  paper_id: string;
  markdown_path: string;
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Extraction data (sidebar tree)
// ---------------------------------------------------------------------------

export interface ExtractionData {
  task: string;
  problem_statement: string;
  key_contributions: string[];
  architecture_components: ArchitectureComponent[];
  datasets: Dataset[];
  metrics_results: MetricResult[];
  limitations: string[];
  future_work: string[];
}

export interface ArchitectureComponent {
  name: string;
  type: string;
  description: string;
}

export interface Dataset {
  name: string;
  size: string;
  modality: string;
}

export interface MetricResult {
  metric: string;
  value: string;
  vs_baseline: string;
}
