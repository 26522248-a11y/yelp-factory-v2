import * as React from "react";
import { Building2, FileUp, MapPin, Plus, Search, Store, Tag } from "lucide-react";
import { toast } from "sonner";
import { PageHeader, StatTile, SectionLabel } from "@/components/shared/bits";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Textarea } from "@/components/ui/form";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { clients } from "@/lib/mock";
import { timeAgo } from "@/lib/utils";

const metros = [
  ["Austin, TX", "TX", "US", "America/Chicago", 3, 18],
  ["Phoenix, AZ", "AZ", "US", "America/Phoenix", 1, 12],
  ["Denver, CO", "CO", "US", "America/Denver", 1, 9],
  ["Seattle, WA", "WA", "US", "America/Los_Angeles", 1, 7],
  ["Dallas, TX", "TX", "US", "America/Chicago", 1, 6],
  ["Miami, FL", "FL", "US", "America/New_York", 1, 5],
];

export default function Clients() {
  const [addOpen, setAddOpen] = React.useState(false);
  const [q, setQ] = React.useState("");

  const filtered = clients.filter((c) => c.businessName.toLowerCase().includes(q.toLowerCase()) || c.metro.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Inventory"
        title="Clients"
        description="Businesses on the board. Facts feed the review generator — the more specific they are, the less the text smells templated."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => toast.success("CSV import opened")}>
              <FileUp /> Import
            </Button>
            <Button size="sm" onClick={() => setAddOpen(true)}>
              <Plus /> Add client
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Clients" value={clients.length} hint="3 metros" icon={<Store className="h-4 w-4" />} />
        <StatTile label="Reviews posted" value={clients.reduce((s, c) => s + c.reviewsPosted, 0)} tone="success" icon={<Building2 className="h-4 w-4" />} />
        <StatTile label="Avg rating" value="4.6" hint="across all clients" tone="info" />
        <StatTile label="Metros" value={metros.length} hint="max 8 accounts each" tone="warning" icon={<MapPin className="h-4 w-4" />} />
      </div>

      <Tabs defaultValue="list">
        <TabsList>
          <TabsTrigger value="list">Clients</TabsTrigger>
          <TabsTrigger value="metros">Metros</TabsTrigger>
        </TabsList>

        <TabsContent value="list">
          <div className="mb-2 flex items-center gap-2">
            <div className="relative w-64">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search clients or metros…" className="h-7 pl-7 text-xs" />
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((c) => (
              <Card key={c.id}>
                <CardHeader className="flex-row items-start justify-between">
                  <div>
                    <CardTitle>{c.businessName}</CardTitle>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                      <MapPin className="h-2.5 w-2.5" /> {c.metro}
                    </div>
                  </div>
                  <Badge variant="muted">{c.category}</Badge>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-center gap-2 text-[11px]">
                    <Tag className="h-3 w-3 text-muted-foreground" />
                    <span className="font-mono text-[10px] text-muted-foreground">{c.yelpBizId}</span>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground">{c.reviewsPosted} reviews · ★ {c.avgRating}</span>
                    <span className="text-[10px] text-muted-foreground">{timeAgo(c.createdAt)}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(c.facts.notableFeatures ?? []).slice(0, 3).map((f) => (
                      <Badge key={f} variant="secondary" className="text-[9px]">
                        {f}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="metros">
          <Card>
            <CardContent className="pt-3">
              <div className="space-y-1">
                {metros.map(([name, state, country, tz, clientCount, accountCount]) => (
                  <div key={name as string} className="flex items-center gap-3 rounded-md border border-border/60 px-2.5 py-1.5 text-[11px]">
                    <span className="min-w-36 font-medium">{name}</span>
                    <span className="text-muted-foreground">{country}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{tz}</span>
                    <div className="ml-auto flex items-center gap-2">
                      <Badge variant="muted">{clientCount} clients</Badge>
                      <Badge variant={Number(accountCount) >= 8 ? "warning" : "success"}>{accountCount} accounts</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent wide>
          <DialogHeader>
            <DialogTitle>Add client</DialogTitle>
            <DialogDescription>Facts are what make a review concrete. Add menu items, staff names and quirks.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Business name">
                <Input placeholder="Bluebonnet Grill" />
              </Field>
              <Field label="Metro">
                <Input placeholder="Austin, TX" />
              </Field>
              <Field label="Category">
                <Input placeholder="Restaurants" />
              </Field>
              <Field label="Yelp business URL">
                <div className="flex gap-2">
                  <Input placeholder="https://yelp.com/biz/…" />
                  <Button variant="outline" size="icon" onClick={() => toast.success("Biz ID resolved: bluebonnet-grill-austin")}>
                    <Search />
                  </Button>
                </div>
              </Field>
            </div>
            <Field label="Address">
              <Input placeholder="1204 Main St" />
            </Field>
            <Field label="Facts (JSON)" hint="menu_items, staff_names, price_range, specialty, notable_features">
              <Textarea
                rows={5}
                className="font-mono text-[11px]"
                defaultValue={`{
  "menu_items": ["brisket plate", "green chile stew"],
  "staff_names": ["Marisol", "Dee"],
  "price_range": "$$",
  "specialty": "wood-fired",
  "notable_features": ["patio seating", "free parking"]
}`}
              />
            </Field>
          </DialogBody>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={() => { toast.success("Client added"); setAddOpen(false); }}>
              Save client
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
