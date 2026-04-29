import MDEditor from "@uiw/react-md-editor";
import { applications } from "../api/applications";

export function AnschreibenEditor({
  appId,
  md,
  onChange,
  hasDocx,
}: {
  appId: string;
  md: string;
  onChange: (v: string) => void;
  hasDocx: boolean;
}) {
  return (
    <div>
      <MDEditor value={md} onChange={(v) => onChange(v ?? "")} height={500} />
      <div className="mt-2 flex gap-2">
        {hasDocx && (
          <a
            href={applications.docxUrl(appId)}
            className="bg-emerald-600 text-white px-4 py-2 rounded"
          >
            Download DOCX
          </a>
        )}
      </div>
    </div>
  );
}
