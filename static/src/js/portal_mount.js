/** @odoo-module **/
import { mount } from "@odoo/owl";
import { ContactsTable } from "./contacts_table";

document.addEventListener("DOMContentLoaded", () => {
  const el = document.getElementById("my_contacts_table_target");
  if (el) {
    console.log("🔧 Montuję ContactsTable ręcznie");
    mount(ContactsTable, { target: el });
  }
});
