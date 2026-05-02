import { useState } from 'react';
import { api } from '../api/client';
import { X, CheckCircle } from 'lucide-react';

interface RCAFormProps {
  workItemId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function RCAForm({ workItemId, onClose, onSuccess }: RCAFormProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    start_time: '',
    end_time: '',
    root_cause_category: 'infra',
    fix_applied: '',
    prevention_steps: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      // Submit RCA
      await api.post(`/incidents/${workItemId}/rca`, form);
      
      // Close incident
      await api.patch(`/incidents/${workItemId}/status`, { status: 'CLOSED' });
      
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to submit RCA');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold">Submit Root Cause Analysis</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X className="w-6 h-6" />
            </button>
          </div>

          {error && (
            <div className="bg-red-50 text-red-700 p-3 rounded-lg mb-4 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Incident Start
                </label>
                <input
                  type="datetime-local"
                  required
                  value={form.start_time}
                  onChange={e => setForm({...form, start_time: e.target.value})}
                  className="w-full border rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Incident End
                </label>
                <input
                  type="datetime-local"
                  required
                  value={form.end_time}
                  onChange={e => setForm({...form, end_time: e.target.value})}
                  className="w-full border rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Root Cause Category
              </label>
              <select
                value={form.root_cause_category}
                onChange={e => setForm({...form, root_cause_category: e.target.value})}
                className="w-full border rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
              >
                <option value="infra">Infrastructure Failure</option>
                <option value="code">Code Bug</option>
                <option value="config">Configuration Error</option>
                <option value="dependency">Third-party Dependency</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Fix Applied <span className="text-gray-400">(min 20 chars)</span>
              </label>
              <textarea
                required
                minLength={20}
                rows={3}
                value={form.fix_applied}
                onChange={e => setForm({...form, fix_applied: e.target.value})}
                placeholder="Describe the fix in detail..."
                className="w-full border rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Prevention Steps <span className="text-gray-400">(min 20 chars)</span>
              </label>
              <textarea
                required
                minLength={20}
                rows={3}
                value={form.prevention_steps}
                onChange={e => setForm({...form, prevention_steps: e.target.value})}
                placeholder="How will we prevent this in the future?"
                className="w-full border rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white" />
              ) : (
                <>
                  <CheckCircle className="w-5 h-5" />
                  Submit RCA & Close Incident
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}