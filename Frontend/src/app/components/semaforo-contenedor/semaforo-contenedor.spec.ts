import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SemaforoContenedor } from './semaforo-contenedor';

describe('SemaforoContenedor', () => {
  let component: SemaforoContenedor;
  let fixture: ComponentFixture<SemaforoContenedor>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SemaforoContenedor],
    }).compileComponents();

    fixture = TestBed.createComponent(SemaforoContenedor);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
