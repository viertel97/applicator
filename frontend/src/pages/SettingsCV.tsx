import { cv } from "../api/documents";
import { VariantSettings } from "./_VariantSettings";

export default function SettingsCV() {
  return <VariantSettings title="CV variants" api={cv} queryKey="cv-variants" />;
}
