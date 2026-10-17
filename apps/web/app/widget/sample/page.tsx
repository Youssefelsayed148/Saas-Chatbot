import { requirePlatformStaff } from "@/lib/staff-access";
import WidgetSample from "./sample";

export default async function WidgetSamplePage() {
  await requirePlatformStaff("/widget/sample");
  return <WidgetSample />;
}
