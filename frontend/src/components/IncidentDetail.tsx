import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { api, type IncidentDetail as IncidentDetailType } from '../api/client.ts';
import { ArrowLeft, Activity, FileText, AlertCircle } from 'lucide-react';
import { RCAForm } from './RCAForm';
import { useState } from 'react';

export function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [showRCA, setShowRCA] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['incident', id],
    queryFn: async () => {
      // const res = await api.get<IncidentDetailType>(`/incidents/${id}`);
      const res = await api.get<IncidentDetailType>(`/incidents/${id}`);
      return res.data;
    },
    refetchInterval: 3000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!data) return <div>Not found</div>;

  const { work_item, signals, signal_count } = data;

  return (
    <div className="max-w-6xl mx-auto p-6">
      <button 
        onClick={() => navigate('/')}
        className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
      >
        <ArrowLeft className="w-5 h-5" />
        Back to Dashboard
      </button>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Work Item Info */}
        <div className="col-span-2 space-y-6">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-2xl font-bold">{work_item.component_id}</h1>
                <p className="text-sm text-gray-500 font-mono">{work_item.id}</p>
              </div>
              <StatusBadge status={work_item.status} severity={work_item.severity} />
            </div>

            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-gray-500">Created</p>
                <p className="font-medium">{new Date(work_item.created_at).toLocaleString()}</p>
              </div>
              {work_item.resolved_at && (
                <div>
                  <p className="text-gray-500">Resolved</p>
                  <p className="font-medium">{new Date(work_item.resolved_at).toLocaleString()}</p>
                </div>
              )}
              {work_item.mttr_seconds && (
                <div>
                  <p className="text-gray-500">MTTR</p>
                  <p className="font-medium">{formatDuration(work_item.mttr_seconds)}</p>
                </div>
              )}
            </div>
          </div>

          {/* Signals */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Activity className="w-5 h-5 text-blue-600" />
              <h2 className="text-lg font-semibold">Raw Signals ({signal_count})</h2>
            </div>
            
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {signals.map((signal, idx) => (
                <div key={idx} className="bg-gray-50 rounded p-3 text-sm">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-xs text-gray-500">
                      {new Date(signal.ingested_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <pre className="text-xs overflow-x-auto">
                    {JSON.stringify(signal.payload, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="space-y-4">
          {work_item.status === 'RESOLVED' && !work_item.rca && (
            <div className="card bg-yellow-50 border-yellow-200">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-5 h-5 text-yellow-600 mt-0.5" />
                <div>
                  <p className="font-medium text-yellow-800">RCA Required</p>
                  <p className="text-sm text-yellow-700 mt-1">
                    Submit Root Cause Analysis to close this incident.
                  </p>
                </div>
              </div>
            </div>
          )}

          {work_item.status !== 'CLOSED' && (
            <div className="card">
              <h3 className="font-semibold mb-3">Actions</h3>
              <div className="space-y-2">
                {work_item.status === 'OPEN' && (
                  <button 
                    onClick={() => updateStatus('INVESTIGATING')}
                    className="w-full btn-primary"
                  >
                    Start Investigation
                  </button>
                )}
                {work_item.status === 'INVESTIGATING' && (
                  <>
                    <button 
                      onClick={() => updateStatus('RESOLVED')}
                      className="w-full btn-primary bg-green-600 hover:bg-green-700"
                    >
                      Mark Resolved
                    </button>
                  </>
                )}
                {work_item.status === 'RESOLVED' && (
                  <button 
                    onClick={() => setShowRCA(true)}
                    className="w-full btn-primary"
                  >
                    Submit RCA & Close
                  </button>
                )}
              </div>
            </div>
          )}

          {work_item.rca && (
            <div className="card">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-5 h-5 text-green-600" />
                <h3 className="font-semibold">Root Cause Analysis</h3>
              </div>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-gray-500">Category</p>
                  <p className="font-medium capitalize">{work_item.rca.root_cause_category}</p>
                </div>
                <div>
                  <p className="text-gray-500">Fix Applied</p>
                  <p className="mt-1">{work_item.rca.fix_applied}</p>
                </div>
                <div>
                  <p className="text-gray-500">Prevention</p>
                  <p className="mt-1">{work_item.rca.prevention_steps}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {showRCA && (
        <RCAForm 
          workItemId={work_item.id} 
          onClose={() => setShowRCA(false)}
          onSuccess={() => {
            setShowRCA(false);
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}

function StatusBadge({ status, severity }: { status: string; severity: string }) {
  const colors = {
    OPEN: 'bg-red-100 text-red-800',
    INVESTIGATING: 'bg-yellow-100 text-yellow-800',
    RESOLVED: 'bg-green-100 text-green-800',
    CLOSED: 'bg-gray-100 text-gray-800',
  };

  return (
    <div className="flex items-center gap-2">
      <span className={`px-3 py-1 rounded-full text-sm font-medium ${colors[status as keyof typeof colors]}`}>
        {status}
      </span>
      <span className={`px-2 py-0.5 rounded text-xs font-bold text-white ${
        severity === 'P0' ? 'bg-red-600' :
        severity === 'P1' ? 'bg-orange-500' :
        severity === 'P2' ? 'bg-yellow-500' : 'bg-blue-500'
      }`}>
        {severity}
      </span>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

async function updateStatus(status: string) {
  // This would be implemented with mutation
  console.log('Update status to', status);
}