import { Paper, OutputBundle } from '@/types';

const API_URL = import.meta.env.VITE_API_URL || '';

export const papersApi = {
  async listPapers(filters?: any): Promise<Paper[]> {
    // Mocking for now if API_URL is not set
    if (!API_URL) return mockPapers;

    const response = await fetch(`${API_URL}/papers`);
    if (!response.ok) throw new Error('Failed to fetch papers');
    return response.json();
  },

  async getPaper(id: string): Promise<Paper> {
    if (!API_URL) return mockPapers.find(p => p.id === id) || mockPapers[0];

    const response = await fetch(`${API_URL}/papers/${id}`);
    if (!response.ok) throw new Error('Failed to fetch paper');
    return response.json();
  },

  async uploadPaper(file: File): Promise<Paper> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_URL}/papers/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) throw new Error('Failed to upload paper');
    return response.json();
  },

  async createFromArxiv(url: string): Promise<Paper> {
    const response = await fetch(`${API_URL}/papers/arxiv`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!response.ok) throw new Error('Failed to ingest from arXiv');
    return response.json();
  },

  async getOutputBundle(id: string): Promise<OutputBundle> {
    if (!API_URL) return mockOutputBundle;

    const response = await fetch(`${API_URL}/papers/${id}/output`);
    if (!response.ok) throw new Error('Failed to fetch output bundle');
    return response.json();
  }
};

const mockPapers: Paper[] = [
  {
    id: '1',
    source: 'ARXIV_URL',
    source_url: 'https://arxiv.org/abs/1706.03762',
    pdf_storage_path: 'papers/1.pdf',
    created_at: new Date().toISOString(),
    metadata: {
      title: 'Attention Is All You Need',
      authors: ['Ashish Vaswani', 'Noam Shazeer', 'Niki Parmar', 'Jakob Uszkoreit'],
      abstract: 'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...',
      venue: 'NeurIPS',
      year: 2017,
      arxiv_id: '1706.03762',
      doi: null,
      page_count: 15,
      domain: 'NLP',
      sub_domain: 'Transformers'
    }
  },
  {
    id: '2',
    source: 'PDF_UPLOAD',
    source_url: null,
    pdf_storage_path: 'papers/2.pdf',
    created_at: new Date().toISOString(),
    metadata: {
      title: 'Generative Adversarial Nets',
      authors: ['Ian Goodfellow', 'Jean Pouget-Abadie', 'Mehdi Mirza'],
      abstract: 'We propose a new framework for estimating generative models via an adversarial process...',
      venue: 'NIPS',
      year: 2014,
      arxiv_id: '1406.2661',
      doi: null,
      page_count: 9,
      domain: 'Computer Vision',
      sub_domain: 'Generative Models'
    }
  }
];

const mockOutputBundle: OutputBundle = {
  paper_id: '1',
  summaries: [
    { level: 'PARAGRAPH', content: 'This paper proposes the Transformer, a new simple network architecture based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.' },
    { level: 'ELI5', content: 'Imagine you are reading a book. Instead of reading one word at a time from start to finish, you can look at the whole page and see which words are most important to understand what is happening right now. That is what this paper does for computers.' }
  ],
  diagrams: [
    {
      diagram_type: 'ARCHITECTURE',
      dsl_code: 'graph TD\n  A[Input] --> B[Encoder]\n  B --> C[Decoder]\n  C --> D[Output]',
      svg_path: '/mock-diagram.svg'
    }
  ],
  code: {
    python_path: 'impl.py',
    notebook_path: 'impl.ipynb',
    synthetic_data_description: 'Generated synthetic sequence data for testing the attention mechanism.'
  },
  report: {
    markdown_path: 'report.md'
  },
  extraction: {
    task: 'Sequence Transduction',
    problem_statement: 'Recurrent models are slow and hard to parallelize.',
    key_contributions: ['Self-attention mechanism', 'Parallelizable architecture', 'State-of-the-art results on translation'],
    architecture_components: [
      { name: 'Multi-Head Attention', type: 'Layer', description: 'Allows the model to jointly attend to information from different representation subspaces.' }
    ],
    datasets: [
      { name: 'WMT 2014 English-to-German', size: '4.5M sentence pairs', modality: 'Text' }
    ],
    metrics_results: [
      { metric: 'BLEU', value: '28.4', vs_baseline: '+2.0' }
    ],
    limitations: ['High memory usage for very long sequences'],
    future_work: ['Scaling to even larger datasets', 'Application to other modalities like images']
  }
};
