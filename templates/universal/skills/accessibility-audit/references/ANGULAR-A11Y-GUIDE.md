# Angular Accessibility Testing Guide

Reference for testing Angular applications with Angular Material for WCAG 2.2 accessibility.

---

## Angular Material Accessibility

Angular Material components are designed with accessibility in mind, but require proper usage.

### Built-in Accessibility Features

| Component | Accessibility Feature |
|-----------|----------------------|
| `mat-button` | Keyboard focus, ARIA roles |
| `mat-form-field` | Label association, error announcements |
| `mat-select` | Listbox role, arrow key navigation |
| `mat-table` | Table semantics, sortable headers |
| `mat-dialog` | Focus trap, escape to close |
| `mat-menu` | Menu role, arrow navigation |
| `mat-checkbox` | Checkbox role, checked state |
| `mat-radio-group` | Radiogroup role, selection state |
| `mat-tab-group` | Tablist role, arrow navigation |
| `mat-expansion-panel` | Button role, expanded state |

---

## Form Accessibility

### Labels and Instructions

```typescript
// ✅ CORRECT - mat-label provides accessible label
<mat-form-field>
  <mat-label>Email Address</mat-label>
  <input matInput type="email" [formControl]="emailControl">
  <mat-hint>We'll never share your email</mat-hint>
</mat-form-field>

// ❌ INCORRECT - Missing label
<mat-form-field>
  <input matInput placeholder="Email">  // Placeholder is NOT a label
</mat-form-field>

// ✅ CORRECT - aria-label for icon-only inputs
<mat-form-field>
  <mat-icon matPrefix>search</mat-icon>
  <input matInput aria-label="Search participants">
</mat-form-field>
```

### Error State Management

```typescript
// ✅ CORRECT - Mat-error with proper ARIA binding
<mat-form-field>
  <mat-label>Agreement ID</mat-label>
  <input matInput [formControl]="agreementId">
  <mat-error *ngIf="agreementId.hasError('required')">
    Agreement ID is required
  </mat-error>
  <mat-error *ngIf="agreementId.hasError('pattern')">
    Agreement ID must be in format A####
  </mat-error>
</mat-form-field>

// Component - Custom error state matcher
@Component({...})
export class FormComponent {
  errorStateMatcher = new ShowOnDirtyErrorStateMatcher();
}
```

### Required Field Indicators

```typescript
// ✅ CORRECT - Visual and programmatic required indicator
<mat-form-field>
  <mat-label>
    Participant Name
    <span class="required-indicator" aria-hidden="true">*</span>
  </mat-label>
  <input matInput [formControl]="name" required>
  <!-- 'required' attribute provides programmatic indication -->
</mat-form-field>

// ✅ ALTERNATIVE - Required in label text
<mat-form-field>
  <mat-label>Participant Name (required)</mat-label>
  <input matInput [formControl]="name" required>
</mat-form-field>
```

### Form Field Grouping

```typescript
// ✅ CORRECT - fieldset/legend for radio groups
<fieldset>
  <legend>Contact Preference</legend>
  <mat-radio-group [formControl]="preference">
    <mat-radio-button value="email">Email</mat-radio-button>
    <mat-radio-button value="phone">Phone</mat-radio-button>
    <mat-radio-button value="mail">Mail</mat-radio-button>
  </mat-radio-group>
</fieldset>

// ✅ CORRECT - aria-labelledby for complex groups
<div role="group" aria-labelledby="address-heading">
  <h3 id="address-heading">Mailing Address</h3>
  <mat-form-field>
    <mat-label>Street</mat-label>
    <input matInput>
  </mat-form-field>
  <!-- ... more address fields -->
</div>
```

---

## Component Patterns

### Buttons

```typescript
// ✅ CORRECT - Descriptive button text
<button mat-raised-button color="primary" (click)="save()">
  Save Participant
</button>

// ❌ INCORRECT - Non-descriptive
<button mat-button (click)="save()">Submit</button>

// ✅ CORRECT - Icon button with aria-label
<button mat-icon-button 
        aria-label="Delete participant"
        (click)="delete()">
  <mat-icon>delete</mat-icon>
</button>

// ❌ INCORRECT - Icon button without label
<button mat-icon-button (click)="delete()">
  <mat-icon>delete</mat-icon>  // Screen reader: "button"
</button>
```

### Dialogs

```typescript
// ✅ CORRECT - Dialog with proper accessibility
openEditDialog() {
  this.dialog.open(EditDialogComponent, {
    ariaLabel: 'Edit Participant Information',
    autoFocus: 'first-tabbable',
    restoreFocus: true,
    data: { participant: this.participant }
  });
}

// Dialog component
@Component({
  template: `
    <h2 mat-dialog-title>Edit Participant</h2>
    <mat-dialog-content>
      <!-- Form content -->
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button mat-dialog-close>Cancel</button>
      <button mat-raised-button color="primary" 
              [mat-dialog-close]="result">Save</button>
    </mat-dialog-actions>
  `
})
export class EditDialogComponent {}
```

### Tables

```typescript
// ✅ CORRECT - Accessible mat-table
<table mat-table [dataSource]="dataSource" 
       aria-label="Participant compliance actions">
  
  <ng-container matColumnDef="name">
    <th mat-header-cell *matHeaderCellDef mat-sort-header>
      Participant Name
    </th>
    <td mat-cell *matCellDef="let row">{{ row.name }}</td>
  </ng-container>

  <ng-container matColumnDef="status">
    <th mat-header-cell *matHeaderCellDef>Status</th>
    <td mat-cell *matCellDef="let row">
      {{ row.status }}
      <span class="sr-only">for {{ row.name }}</span>
    </td>
  </ng-container>

  <ng-container matColumnDef="actions">
    <th mat-header-cell *matHeaderCellDef>
      <span class="sr-only">Actions</span>
    </th>
    <td mat-cell *matCellDef="let row">
      <button mat-icon-button 
              [attr.aria-label]="'Edit ' + row.name"
              (click)="edit(row)">
        <mat-icon>edit</mat-icon>
      </button>
    </td>
  </ng-container>

  <tr mat-header-row *matHeaderRowDef="displayedColumns"></tr>
  <tr mat-row *matRowDef="let row; columns: displayedColumns"></tr>
</table>
```

### Menus

```typescript
// ✅ CORRECT - Menu with keyboard support
<button mat-button [matMenuTriggerFor]="actionsMenu"
        aria-label="Participant actions menu">
  Actions
  <mat-icon>arrow_drop_down</mat-icon>
</button>
<mat-menu #actionsMenu="matMenu">
  <button mat-menu-item (click)="edit()">
    <mat-icon>edit</mat-icon>
    <span>Edit</span>
  </button>
  <button mat-menu-item (click)="delete()">
    <mat-icon>delete</mat-icon>
    <span>Delete</span>
  </button>
</mat-menu>
```

### Expansion Panels

```typescript
// ✅ CORRECT - Accessible expansion panel
<mat-accordion>
  <mat-expansion-panel>
    <mat-expansion-panel-header>
      <mat-panel-title>Personal Information</mat-panel-title>
      <mat-panel-description>
        Name, contact details, and preferences
      </mat-panel-description>
    </mat-expansion-panel-header>
    
    <!-- Panel content -->
  </mat-expansion-panel>
</mat-accordion>
```

---

## Live Regions and Announcements

### Status Updates

```typescript
// ✅ CORRECT - Live region for status updates
<div aria-live="polite" aria-atomic="true" class="sr-only">
  {{ statusMessage }}
</div>

// Component
updateStatus(message: string) {
  this.statusMessage = message;
}

// Usage
this.updateStatus('Participant saved successfully');
```

### Loading States

```typescript
// ✅ CORRECT - Announce loading state
<div *ngIf="loading" 
     role="status" 
     aria-live="polite">
  <mat-spinner diameter="24"></mat-spinner>
  <span class="sr-only">Loading participant data...</span>
</div>

// ✅ CORRECT - Loading completed announcement
<div aria-live="polite" class="sr-only">
  <span *ngIf="!loading && dataLoaded">
    Participant data loaded. {{ participants.length }} participants found.
  </span>
</div>
```

### Error Announcements

```typescript
// ✅ CORRECT - Alert role for errors
<div *ngIf="errorMessage" 
     role="alert" 
     class="error-banner">
  <mat-icon>error</mat-icon>
  {{ errorMessage }}
</div>
```

---

## Focus Management

### Focus After Actions

```typescript
// ✅ CORRECT - Return focus after delete
async deleteParticipant(index: number) {
  await this.participantService.delete(this.participants[index].id);
  this.participants.splice(index, 1);
  
  // Focus next item or previous if last
  const focusIndex = Math.min(index, this.participants.length - 1);
  if (focusIndex >= 0) {
    this.focusRow(focusIndex);
  } else {
    this.addButton.nativeElement.focus();
  }
}
```

### Skip Links

```typescript
// ✅ CORRECT - Skip link in app component
@Component({
  template: `
    <a class="skip-link" href="#main-content">
      Skip to main content
    </a>
    <app-header></app-header>
    <app-navigation></app-navigation>
    <main id="main-content" tabindex="-1">
      <router-outlet></router-outlet>
    </main>
  `,
  styles: [`
    .skip-link {
      position: absolute;
      left: -9999px;
      top: auto;
      width: 1px;
      height: 1px;
      overflow: hidden;
    }
    .skip-link:focus {
      position: fixed;
      top: 0;
      left: 0;
      width: auto;
      height: auto;
      padding: 1rem;
      background: #005fcc;
      color: white;
      z-index: 9999;
    }
  `]
})
export class AppComponent {}
```

### Route Change Focus

```typescript
// ✅ CORRECT - Focus main content on route change
@Component({...})
export class AppComponent implements OnInit {
  @ViewChild('mainContent') mainContent: ElementRef;

  constructor(private router: Router) {}

  ngOnInit() {
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe(() => {
      // Focus main content area
      this.mainContent.nativeElement.focus();
    });
  }
}
```

---

## Screen Reader Only Content

```scss
// ✅ Utility class for screen-reader-only content
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

// Allow focus on sr-only elements
.sr-only-focusable:focus {
  position: static;
  width: auto;
  height: auto;
  margin: 0;
  overflow: visible;
  clip: auto;
  white-space: normal;
}
```

Usage:
```typescript
// ✅ CORRECT - Additional context for screen readers
<button mat-icon-button (click)="download()">
  <mat-icon>download</mat-icon>
  <span class="sr-only">Download compliance report</span>
</button>

// ✅ CORRECT - Table cell context
<td>Active <span class="sr-only">status for participant John Doe</span></td>
```

---

## Testing Tools

### Built-in Tools
```typescript
// Component test for accessibility
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

describe('FormComponent Accessibility', () => {
  it('should have accessible labels for all form controls', () => {
    const inputs = fixture.debugElement.queryAll(By.css('input, select, textarea'));
    
    inputs.forEach(input => {
      const el = input.nativeElement;
      const hasLabel = 
        el.getAttribute('aria-label') ||
        el.getAttribute('aria-labelledby') ||
        document.querySelector(`label[for="${el.id}"]`);
      
      expect(hasLabel).toBeTruthy(
        `Input ${el.name || el.id} missing accessible label`
      );
    });
  });

  it('should have visible focus indicators', () => {
    const button = fixture.debugElement.query(By.css('button'));
    button.nativeElement.focus();
    
    const styles = window.getComputedStyle(button.nativeElement);
    expect(styles.outline).not.toBe('none');
  });
});
```

### CDK A11y Module

```typescript
import { A11yModule, LiveAnnouncer, FocusMonitor } from '@angular/cdk/a11y';

@Component({...})
export class MyComponent {
  constructor(
    private liveAnnouncer: LiveAnnouncer,
    private focusMonitor: FocusMonitor
  ) {}

  announceStatus(message: string) {
    this.liveAnnouncer.announce(message, 'polite');
  }

  ngAfterViewInit() {
    // Monitor focus origin (mouse, keyboard, touch, programmatic)
    this.focusMonitor.monitor(this.myElement).subscribe(origin => {
      if (origin === 'keyboard') {
        // Apply keyboard-specific focus styles
      }
    });
  }
}
```

---

## Common Issues Checklist

| Issue | Check | Fix |
|-------|-------|-----|
| Missing labels | `mat-form-field` without `mat-label` | Add `<mat-label>` |
| Icon-only buttons | No `aria-label` | Add `aria-label` attribute |
| Custom controls | Missing ARIA | Add `role`, `aria-*` attributes |
| Focus not visible | CSS `outline: none` | Use `:focus-visible` |
| Route change | Focus not managed | Focus main content on navigate |
| Dynamic content | Not announced | Use `aria-live` regions |
| Table actions | Ambiguous | Add context with `sr-only` |
| Modals | Focus not trapped | Use `mat-dialog` or CDK |
| Errors | Not associated | Use `aria-describedby` |
| Loading | Not announced | Use `role="status"` |

---

*Reference: Angular Material Accessibility, Angular CDK A11y Module*
*Last Updated: February 2025*
