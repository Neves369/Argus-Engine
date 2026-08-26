export type SessionStatus = 'in_progress' | 'completed' | 'failed';

export interface Session {
  id: string;
  target: string;
  startTime: string;
  endTime: string;
  status: SessionStatus;
}

export const DEFAULT_SESSIONS: Session[] = [
  {
    id: 'sess-001',
    target: 'Alvo 1',
    startTime: '08:00',
    endTime: '09:15',
    status: 'completed',
  },
  {
    id: 'sess-002',
    target: 'Alvo 2',
    startTime: '09:30',
    endTime: '10:45',
    status: 'completed',
  },
  {
    id: 'sess-003',
    target: 'Alvo 3',
    startTime: '11:00',
    endTime: '11:40',
    status: 'failed',
  },
  {
    id: 'sess-004',
    target: 'Alvo 4',
    startTime: '13:20',
    endTime: '14:05',
    status: 'completed',
  },
  {
    id: 'sess-005',
    target: 'Alvo 5',
    startTime: '14:30',
    endTime: '—',
    status: 'in_progress',
  },
];
