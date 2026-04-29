import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { applications } from "../api/applications";
import { AddApplicationForm } from "../components/AddApplicationForm";
import { JobStateBadge, StatusBadge } from "../components/StatusBadge";

export default function ApplicationsList() {
  const { data, isLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: applications.list,
    refetchInterval: (q) => {
      const arr = q.state.data;
      if (!arr) return false;
      const inFlight = arr.some(
        (a) => !["ready", "failed"].includes(a.job_state),
      );
      return inFlight ? 2000 : false;
    },
  });
  return (
    <div className="max-w-4xl mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Applications</h1>
      <AddApplicationForm />
      {isLoading && <div>Loading…</div>}
      <ul className="divide-y border rounded bg-white">
        {(data ?? []).map((a) => (
          <li key={a.id} className="p-3 flex items-center gap-3 hover:bg-slate-50">
            <Link to={`/applications/${a.id}`} className="flex-1 truncate">
              <div className="font-medium">{a.job_posting?.title ?? a.url}</div>
              <div className="text-sm text-slate-500">{a.job_posting?.company}</div>
            </Link>
            <JobStateBadge state={a.job_state} />
            <StatusBadge status={a.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
