import { anschreiben } from "../api/documents";
import { VariantSettings } from "./_VariantSettings";

export default function SettingsAnschreiben() {
  return (
    <VariantSettings
      title="Anschreiben templates"
      api={anschreiben}
      queryKey="anschreiben-variants"
    />
  );
}
