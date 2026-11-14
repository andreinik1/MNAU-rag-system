export interface Source {
  source_file: string;
  source_url?: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
}