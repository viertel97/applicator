import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { inquiryPrompt } from "../api/inquiry";

export default function SettingsInquiryPrompt() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["inquiry-prompt"],
    queryFn: () => inquiryPrompt.get(),
  });
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (q.data && !dirty) setDraft(q.data.source_md);
  }, [q.data, dirty]);

  const save = useMutation({
    mutationFn: (s: string) => inquiryPrompt.put(s),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["inquiry-prompt"] });
    },
  });

  if (q.isLoading) return <div className="p-6">Loading…</div>;
  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-2">Pre-application inquiry prompt</h1>
      <p className="text-sm text-slate-500 mb-3">
        System prompt used when drafting the pre-application email. The body of
        the email is built automatically and only includes the topics not
        already covered by the posting (home office, 80% Mon–Thu).
      </p>
      <textarea
        className="border rounded p-2 w-full font-mono text-sm"
        rows={18}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setDirty(true);
        }}
      />
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          className="bg-blue-600 text-white px-3 py-1 rounded disabled:opacity-50"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate(draft)}
        >
          Save
        </button>
        {save.isError && (
          <span className="text-rose-600 text-sm">
            {(save.error as Error).message}
          </span>
        )}
      </div>
    </div>
  );
}
