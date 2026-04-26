export interface Paper {
  id: string;
  source: 'PDF_UPLOAD' | 'ARXIV_URL' | 'DOI';
  source_url: string | null;
  pdf_storage_path: string;
  metadata: PaperMetadata;
  created_at: string;
}

export interface PaperMetadata {
  title: string;
  authors: string[];
  abstract: string;
  venue: string | null;
  year: number | null;
  arxiv_id: string | null;
  doi: string | null;
  page_count: number | null;
  domain: string;
  sub_domain: string;
}

export interface PipelineRun {
  id: string;
  paper_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PARTIAL';
  stages: Record<string, StageResult>;
  started_at: string;
  completed_at: string | null;
  total_tokens: number | null;
  error: string | null;
}

export interface StageResult {
  stage_name: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'SKIPPED' | 'CACHED';
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  cached: boolean;
  token_count: number | null;
}

export interface OutputBundle {
  paper_id: string;
  summaries: SummaryOutput[];
  diagrams: DiagramOutput[];
  code: CodeOutput | null;
  report: ReportOutput | null;
  extraction: ExtractionData | null;
}

export interface SummaryOutput {
  level: 'PARAGRAPH' | 'SECTION_BY_SECTION' | 'BULLETS' | 'ELI5';
  content: string;
}

export interface DiagramOutput {
  diagram_type: 'ARCHITECTURE' | 'TRAINING_FLOW' | 'INFERENCE_FLOW';
  dsl_code: string;
  svg_path: string;
}

export interface CodeOutput {
  python_path: string;
  notebook_path: string;
  synthetic_data_description: string;
}

export interface ReportOutput {
  markdown_path: string;
}

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
