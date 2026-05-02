import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { api, type WorkItem } from '../api/client';
import { AlertTriangle, Clock, Activity } from 'lucide-react';
import { Link } from 'react-router-dom';

const SEVERITY_CONFIG = {
  P0: { color: 'bg-red-600', label: 'CRITICAL', icon: AlertTriangle },
  P1: { color: 'bg-orange-500', label: 'HIGH', icon: AlertTriangle },
  P2: { color: 'bg-yellow-500', label: 'MEDIUM', icon: Activity },
  P3: { color: 'bg-blue-500', label: 'LOW', icon: Activity },
};

const STATUS_COLORS = {
  OPEN: 'bg-red-100 text-red-800',
  INVESTIGATING: 'bg-yellow-100 text-yellow-800',
  RESOLVED: 'bg-green-100 text-green-800',
  CLOSED: 'bg-gray-100 text-gray-800',
};

export function Dashboard() {
  const queryClient = useQueryClient();

  const { data: incidents, isLoading } = useQuery({
    queryKey: ['active-incidents'],
    queryFn: async () => {
      const res = await api.get<WorkItem[]>('/incidents/active');
      return res.data;
    },
    refetchInterval: 3000, // Poll every 3 seconds
  });

  // WebSocket for real-time updates (fallback to polling)
  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/ws/dashboard');
    
    ws.onmessage = () => {
      queryClient.invalidateQueries({ queryKey: ['active-incidents'] });
    };

    return () => ws.close();
  }, [queryClient]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const sorted = incidents?.sort((a, b) => {
    const weight = { P0: 4, P1: 3, P2: 2, P3: 1 };
    return weight[b.severity] - weight[a.severity];
  });

  return (
    <div className="max-w-7xl mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Incident Management Dashboard</h1>
        <p className="text-gray-600 mt-1">Real-time monitoring of active incidents</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {(['P0', 'P1', 'P2', 'P3'] as const).map((sev) => {
          const count = incidents?.filter(i => i.severity === sev).length || 0;
          const config = SEVERITY_CONFIG[sev];
          return (
            <div key={sev} className={`${config.color} text-white rounded-lg p-4`}>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm opacity-90">{config.label}</p>
                  <p className="text-2xl font-bold">{count}</p>
                </div>
                <config.icon className="w-8 h-8 opacity-75" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Incident List */}
      <div className="space-y-3">
        {sorted?.map((incident: any) => (
          <IncidentCard key={incident.id} incident={incident} />
        ))}
        
        {sorted?.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <Activity className="w-12 h-12 mx-auto mb-3 opacity-50" />
            <p>No active incidents</p>
          </div>
        )}
      </div>
    </div>
  );
}

function IncidentCard({ incident }: { incident: WorkItem }) {
  const config = SEVERITY_CONFIG[incident.severity];
  const StatusIcon = config.icon;

  return (
    <Link to={`/incident/${incident.id}`}>
      <div className="card hover:shadow-lg transition-shadow cursor-pointer border-l-4"
           style={{ borderLeftColor: incident.severity === 'P0' ? '#dc2626' : 
                                     incident.severity === 'P1' ? '#ea580c' :
                                     incident.severity === 'P2' ? '#ca8a04' : '#2563eb' }}>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className={`${config.color} text-white text-xs px-2 py-0.5 rounded font-semibold`}>
                {incident.severity}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[incident.status]}`}>
                {incident.status}
              </span>
            </div>
            
            <h3 className="font-semibold text-lg">{incident.component_id}</h3>
            <p className="text-sm text-gray-500 font-mono">{incident.id}</p>
          </div>

          <div className="text-right">
            {incident.mttr_seconds && (
              <div className="flex items-center gap-1 text-sm text-gray-600">
                <Clock className="w-4 h-4" />
                <span>{formatDuration(incident.mttr_seconds)}</span>
              </div>
            )}
            <p className="text-xs text-gray-400 mt-1">
              {new Date(incident.created_at).toLocaleString()}
            </p>
          </div>
        </div>
      </div>
    </Link>
  );
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}