-- schema.sql

-- doctors_registration
-- Directly migrated from the old database with original structure, 
-- though key types remain unspecified
CREATE TABLE doctors_registration (
  id SERIAL PRIMARY KEY,
  Fname VARCHAR(100) NOT NULL,
  Mname VARCHAR(100) DEFAULT '',
  Lname VARCHAR(100) NOT NULL,
  Age INTEGER,
  bloodGroup VARCHAR(10),
  MobileNumber VARCHAR(20) NOT NULL,
  EmailId VARCHAR(150) UNIQUE NOT NULL,
  Location1 VARCHAR(200) NOT NULL,
  Location2 VARCHAR(200),
  PostalCode VARCHAR(15),
  City VARCHAR(100) NOT NULL,
  Province VARCHAR(100) NOT NULL,
  Country VARCHAR(100) NOT NULL,
  Latitude DECIMAL(9,6),
  Longitude DECIMAL(9,6),
  Medical_LICENSE_Number VARCHAR(50) UNIQUE NOT NULL,
  DLNumber VARCHAR(50),
  Specialization VARCHAR(200) NOT NULL,
  PractincingHospital VARCHAR(200),
  Gender VARCHAR(20),
  uuid VARCHAR(36) UNIQUE NOT NULL,
  password VARCHAR(200) NOT NULL,
  verification INTEGER DEFAULT 0,
  Availability INTEGER DEFAULT 1,
  date_of_birth DATE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_doctors_email ON doctors_registration (EmailId);
CREATE INDEX idx_doctors_specialization ON doctors_registration (Specialization);
CREATE INDEX idx_doctors_location ON doctors_registration (City, Province);



-- patients_registration
-- Directly migrated from the old database with original structure, 
-- though key types remain unspecified
CREATE TABLE patients_registration (
  id SERIAL PRIMARY KEY,
  FName VARCHAR(100) NOT NULL,
  MName VARCHAR(100) DEFAULT '',
  LName VARCHAR(100) NOT NULL,
  Age INTEGER,
  BloodGroup VARCHAR(10),
  Gender VARCHAR(20),
  height VARCHAR(15),  -- Stored as string to accommodate units if needed
  weight VARCHAR(15),  -- Stored as string to accommodate units if needed
  race VARCHAR(100),
  MobileNumber VARCHAR(20) NOT NULL,
  EmailId VARCHAR(150) UNIQUE NOT NULL,
  Address VARCHAR(200) NOT NULL,
  Location VARCHAR(200),
  City VARCHAR(100) NOT NULL,
  Province VARCHAR(100) NOT NULL,
  PostalCode VARCHAR(15),
  Latitude DECIMAL(9,6),
  Longitude DECIMAL(9,6),
  HCardNumber VARCHAR(50),  -- Health Card Number
  PassportNumber VARCHAR(50),
  PRNumber VARCHAR(50),     -- Permanent Resident Number
  DLNumber VARCHAR(50),     -- Driver's License Number
  uuid VARCHAR(36) UNIQUE NOT NULL,
  password VARCHAR(200) NOT NULL,
  verification INTEGER DEFAULT 0,
  date_of_birth DATE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_patients_email ON patients_registration (EmailId);
CREATE INDEX idx_patients_mobile ON patients_registration (MobileNumber);
CREATE INDEX idx_patients_location ON patients_registration (City, Province);
CREATE INDEX idx_patients_identity ON patients_registration (HCardNumber) WHERE HCardNumber IS NOT NULL;


-- ───────────────────────────────────New───────────────────────────────────────

-- 1. Define 
-- doctor_appointment_requests can only be inserted when doctor_available_time_segments.status = 0 (available),
-- and the segment doctor_available_time_segments.status is automatically set to -1 (blocked) after insertion;
-- it will be restored to 0 (available) after the request is canceled (doctor_appointment_requests.status = -1).

-- doctor_appointment can only be inserted when doctor_available_time_segments.status = 0 (available),
-- and doctor_available_time_segments.status will be set to 1 (booked) after insertion;
-- it will be automatically restored to 0 (available) after cancellation (doctor_appointment.status = -1).

-- Status codes explanation:
--   -1 = blocked (doctor self-use/not available/event block)
--    0 = available (open for booking)
--    1 = booked (appointment confirmed)

-- All tables with updated_at columns have the update_updated_at trigger
-- to automatically maintain the timestamp.

-- audit_log uses triggers to track:
--   - Appointment status changes (through doctor_appointment table)
--   - Request status changes (through doctor_appointment_requests table)
-- All audit records are stored in the same table for unified tracking.

-- The doctor_shifts table stores doctor working schedules,
-- which are used to generate available time segments (doctor_available_time_segments).

-- ──────────────────────────────────────────────────────────────────────────


-- 2. doctor_shifts (*new table)
-- Introduced to facilitate mock doctor_available_time_segments generation.
CREATE TABLE doctor_shifts (
  shift_id    SERIAL        PRIMARY KEY,
  doctor_id   INTEGER       NOT NULL
                    REFERENCES doctors_registration(id)
                    ON DELETE CASCADE,
  start_time  TIMESTAMPTZ   NOT NULL,
  end_time    TIMESTAMPTZ   NOT NULL,
  created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_shift_range CHECK (end_time > start_time)
);


-- 3. doctor_available_time_segments
-- doctor_available_time_segments – The central calendar for doctors. 
-- All related tables (events, appointments, blocks) must link to this table.
-- Status Definitions:
-- -1 (Blocked) – Unavailable due to leave, workshops, or other events.
-- 0 (Available) – Free for scheduling events or appointments.
-- 1 (Booked) – Occupied by a patient appointment.
CREATE TABLE doctor_available_time_segments (
  id SERIAL PRIMARY KEY,
  doctor_id INTEGER NOT NULL REFERENCES doctors_registration(id) ON DELETE CASCADE,
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ NOT NULL,
  status SMALLINT NOT NULL DEFAULT 0, -- -1=blocked, 0=available, 1=booked
  category SMALLINT,
  book_count INTEGER DEFAULT 0,
  description VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_time_range CHECK (end_time > start_time)
);


-- 4. doctor_appointment_requests
-- Serves as an interim events table (since legacy DB lacked a dedicated events table). 
-- Currently used exclusively for tracking doctor events.
-- Status values:
-- -1 = Canceled (record remains in table; cancellation is logged in audit_log with user details)
-- 1 = Booked (event is confirmed/scheduled)
CREATE TABLE doctor_appointment_requests (
  id SERIAL PRIMARY KEY,
  patient_id INTEGER REFERENCES patients_registration(id) ON DELETE CASCADE,
  doctor_id INTEGER NOT NULL REFERENCES doctors_registration(id) ON DELETE CASCADE,
  time_segment_id INTEGER NOT NULL REFERENCES doctor_available_time_segments(id) ON DELETE CASCADE,
  category SMALLINT,
  status SMALLINT NOT NULL DEFAULT 0,
  description VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. doctor_appointment
-- Dedicated table for tracking patient-doctor appointments.
-- Status definitions:
-- -1 = Cancelled (record remains in table; cancellation is logged in audit_log with user details)
-- 1 = Booked (confirmed appointment)
CREATE TABLE doctor_appointment (
  appointment_id SERIAL PRIMARY KEY,
  doctor_id INTEGER NOT NULL REFERENCES doctors_registration(id) ON DELETE CASCADE,
  patient_id INTEGER NOT NULL REFERENCES patients_registration(id) ON DELETE CASCADE,
  time_segment_id INTEGER NOT NULL REFERENCES doctor_available_time_segments(id) ON DELETE CASCADE,
  appointment_time TIMESTAMPTZ NOT NULL,
  status SMALLINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_doctor_time ON doctor_available_time_segments(doctor_id, start_time);
CREATE INDEX idx_appointment_patient ON doctor_appointment(patient_id);
CREATE INDEX idx_request_patient ON doctor_appointment_requests(patient_id);
-- Replace the unique index and only restrict active appointments to not be repeated
CREATE UNIQUE INDEX uq_active_time_segment ON doctor_appointment(time_segment_id) WHERE status != -1;

-- 6. Patient-doctor
-- Registry mapping patients to their assigned primary family doctor
CREATE TABLE patient_doctor (
  id                      SERIAL       PRIMARY KEY,
  patient_id              INTEGER      NOT NULL
                             REFERENCES patients_registration(id)
                             ON DELETE CASCADE,
  doctor_id               INTEGER      NOT NULL
                             REFERENCES doctors_registration(id)
                             ON DELETE CASCADE,
  relationship_start_date DATE         NOT NULL DEFAULT CURRENT_DATE,
  relationship_status     VARCHAR(100) NOT NULL DEFAULT 'active',
  association_type        VARCHAR(100),
  record_date             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_patient_doctor UNIQUE (patient_id, doctor_id)
);

-- Enforces one binding record max per patient-doctor pair
-- Patients can have multiple doctors (one-to-many)
-- Unique constraint on (patient_id + doctor_id) prevents duplicates


-- 7. audit_log
-- audit_log uses triggers to track:
--   - Appointment status changes (through doctor_appointment table)
--   - Request status changes (through doctor_appointment_requests table)
-- All audit records are stored in the same table for unified tracking.
CREATE TABLE audit_log (
  id           SERIAL PRIMARY KEY,
  entity       TEXT NOT NULL,      -- e.g., 'doctor_appointment'
  entity_id    INTEGER NOT NULL,
  action       TEXT NOT NULL,      -- e.g., 'cancelled', 'confirmed'
  performed_by INTEGER NOT NULL,   -- patient_id or doctor_id
  role         TEXT CHECK (role IN ('doctor', 'patient')),
  details      JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


--conversations 
-- Serves as a memory store for various interaction data including:
-- User-bot dialogue history
-- slot_mapping
-- task_id
-- input_mode
-- Other contextual conversation elements
CREATE TABLE conversations (
  id SERIAL PRIMARY KEY,
  session_id UUID NOT NULL,
  patient_id INTEGER REFERENCES patients_registration(id) ON DELETE CASCADE,
  doctor_id INTEGER REFERENCES doctors_registration(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('doctor', 'patient')),
  input TEXT NOT NULL,          -- User input
  response TEXT,                -- Natural language returned by the backend LLM (text field)）
  meta JSONB,                   -- Store slot_mapping
  input_mode TEXT DEFAULT 'text' CHECK (input_mode IN ('text', 'voice')), 
  task_id TEXT DEFAULT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
--ALTER TABLE conversations ADD COLUMN meta JSONB;
-- Index suggestions (for session aggregation)
CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_patient ON conversations(patient_id);
CREATE INDEX idx_conversations_doctor ON conversations(doctor_id);

-- ──────────────────────────────────────────────────────────────────────────
-- 8. General trigger function: automatically update updated_at

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Mount triggers only for tables with an updated_at column
CREATE OR REPLACE FUNCTION install_updated_at_triggers()
RETURNS void AS $$
DECLARE
  table_record RECORD;
  trigger_name TEXT;
BEGIN
  -- Loop through all tables that have an updated_at column
  FOR table_record IN 
    SELECT table_name 
    FROM information_schema.columns 
    WHERE column_name = 'updated_at' 
    AND table_schema = 'public'
  LOOP
    trigger_name := 'trg_' || table_record.table_name || '_updated';
    
    -- Check if trigger already exists
    IF NOT EXISTS (
      SELECT 1 
      FROM pg_trigger 
      WHERE tgname = trigger_name
    ) THEN
      EXECUTE format('
        CREATE TRIGGER %I
        BEFORE UPDATE ON %I
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at()', 
        trigger_name, table_record.table_name);
      
      RAISE NOTICE 'Created trigger % on table %', trigger_name, table_record.table_name;
    ELSE
      RAISE NOTICE 'Trigger % already exists on table %', trigger_name, table_record.table_name;
    END IF;
  END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Install trigger
SELECT install_updated_at_triggers();




-- Create an event trigger to automatically add a trigger when a new table is created
CREATE OR REPLACE FUNCTION on_ddl_create_table()
RETURNS event_trigger AS $$
DECLARE
    obj RECORD;
    has_updated_at BOOLEAN;
    trigger_name TEXT;
BEGIN
    FOR obj IN SELECT * FROM pg_event_trigger_ddl_commands()
    LOOP
        IF obj.object_type = 'table' THEN
            -- Check if the new table has an updated_at column
            EXECUTE format('
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = %L 
                    AND column_name = ''updated_at''
                )', obj.objid::regclass)
            INTO has_updated_at;
            
            IF has_updated_at THEN
                -- Build trigger name
                trigger_name := 'trg_' || obj.objid::regclass || '_updated';
                
                -- Check if the trigger already exists
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger 
                    WHERE tgname = trigger_name
                    AND tgrelid = obj.objid
                ) THEN
                    EXECUTE format('
                        CREATE TRIGGER %I
                        BEFORE UPDATE ON %I
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at()',
                        trigger_name, obj.objid::regclass);
                END IF;
            END IF;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- rebuild trigger
DROP EVENT TRIGGER IF EXISTS trg_on_create_table;

CREATE EVENT TRIGGER trg_on_create_table
ON ddl_command_end
WHEN TAG IN ('CREATE TABLE')
EXECUTE FUNCTION on_ddl_create_table();


-- ──────────────────────────────────────────────────────────────────────────
-- 9. doctor_appointment_requests related triggers 

-- create_appointment_request_atomic
DROP FUNCTION IF EXISTS create_appointment_request_atomic(INT, INT, TEXT);

CREATE OR REPLACE FUNCTION create_appointment_request_atomic(
    p_segment_id INT,
    p_doctor_id INT,
    p_request_description TEXT
)
RETURNS JSONB
LANGUAGE plpgsql AS $$
DECLARE
    v_status SMALLINT;
    v_resp JSONB;
BEGIN
    -- Lock the segment row
    SELECT status INTO v_status FROM doctor_available_time_segments 
    WHERE id = p_segment_id FOR UPDATE;

    IF v_status <> 0 THEN
        RAISE EXCEPTION 'Segment not available (status=0 required)';
    END IF;

   
    -- Insert request with status = 1 (confirmed)
    WITH inserted AS (
        INSERT INTO doctor_appointment_requests(time_segment_id, doctor_id, description, status)
        VALUES (p_segment_id, p_doctor_id, p_request_description, 1)
        RETURNING id, time_segment_id, doctor_id, description, created_at, status
    )
    SELECT to_jsonb(inserted.*) INTO v_resp FROM inserted;

    -- Update segment status
    UPDATE doctor_available_time_segments SET status = -1 WHERE id = p_segment_id;

    RETURN v_resp;
END;
$$;




    -- Insert the request and capture all returned values into local variables
    RAISE NOTICE 'Inserting event...';
    INSERT INTO doctor_appointment_requests(time_segment_id, doctor_id, description)
    VALUES (p_segment_id, p_doctor_id, p_request_description)
    RETURNING 
        doctor_appointment_requests.id, 
        doctor_appointment_requests.time_segment_id, 
        doctor_appointment_requests.doctor_id, 
        doctor_appointment_requests.description, 
        doctor_appointment_requests.created_at
    INTO 
        v_request_id, 
        v_time_segment_id, 
        v_doctor_id, 
        v_description, 
        v_created_at;

    -- Update the time segment status to blocked (-1)
    UPDATE doctor_available_time_segments SET status = -1 WHERE id = p_segment_id;

    RAISE NOTICE ' Event created at segment %', p_segment_id;

    -- Assign values to output parameters
    request_id := v_request_id;
    time_segment_id := v_time_segment_id;
    doctor_id := v_doctor_id;
    description := v_description;
    created_at := v_created_at;
    
    RETURN NEXT;
END;
$$;

-- cancel_appointment_request_atomic 
DROP FUNCTION cancel_appointment_request_atomic(integer,integer);
CREATE OR REPLACE FUNCTION cancel_appointment_request_atomic(
    doctorid INT,
    segmentid INT
)
RETURNS TEXT
LANGUAGE plpgsql AS $$
DECLARE
    request_id INT;
BEGIN
    --Step 1: Find the doctor's valid self-use events on the segment (status = 1)
    SELECT id INTO request_id
    FROM doctor_appointment_requests
    WHERE doctor_id = doctorid AND time_segment_id = segmentid AND status = 1
    FOR UPDATE;

    IF request_id IS NULL THEN
        RAISE EXCEPTION 'No such active event for this doctor and segment';
    END IF;

    -- Step 2: Mark as Canceled
    UPDATE doctor_appointment_requests
    SET status = -1, updated_at = NOW()
    WHERE id = request_id;

    -- Step 3: Restore the slot's available status
    UPDATE doctor_available_time_segments
    SET status = 0, updated_at = NOW()
    WHERE id = segmentid;

    RETURN 'OK';
END;
$$;



-- Function to update book_count automatically

CREATE OR REPLACE FUNCTION update_book_count()
RETURNS TRIGGER AS $$
DECLARE
    segment_id INT;
    is_booked BOOLEAN;
BEGIN
    IF TG_TABLE_NAME = 'doctor_appointment' THEN
        segment_id = NEW.time_segment_id;
        is_booked = (NEW.status = 1);
    ELSIF TG_TABLE_NAME = 'doctor_appointment_requests' THEN
        segment_id = NEW.time_segment_id;
        is_booked = (NEW.status = 1);
    ELSE
        RETURN NEW;
    END IF;

    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        UPDATE doctor_available_time_segments 
        SET book_count = CASE WHEN is_booked THEN 1 ELSE 0 END 
        WHERE id = segment_id;

    ELSIF TG_OP = 'DELETE' THEN
        UPDATE doctor_available_time_segments 
        SET status = 0, book_count = 0 
        WHERE id = OLD.time_segment_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- Create triggers for both tables
CREATE TRIGGER trg_update_book_count_appointment
AFTER INSERT OR UPDATE OR DELETE ON doctor_appointment
FOR EACH ROW EXECUTE FUNCTION update_book_count();

CREATE TRIGGER trg_update_book_count_request
AFTER INSERT OR UPDATE OR DELETE ON doctor_appointment_requests
FOR EACH ROW EXECUTE FUNCTION update_book_count();


-- ──────────────────────────────────────────────────────────────────────────
-- 10. Atomic appointment related triggers 
-- Stored procedure (function + explicit transaction + FOR UPDATE lock) combines the three steps of "check-insert-update" into one

-- Atomic book appointment function 
CREATE OR REPLACE FUNCTION book_appointment_atomic(
    p_segment_id INT,
    p_patient_id INT
)
RETURNS TABLE(
    appointment_id INT, 
    time_segment_id INT, 
    patient_id INT, 
    status SMALLINT
)
LANGUAGE plpgsql AS $$
DECLARE
    v_segment_status SMALLINT;
    v_start_time TIMESTAMPTZ;
    v_doctor_id INT;
    v_appointment_id INT;
    v_time_segment_id INT;
    v_return_patient_id INT;
    v_appointment_status SMALLINT;
BEGIN
    -- 1. Row-level locking of time segment with doctor_id retrieval
    SELECT d.status, d.start_time, d.doctor_id 
    INTO v_segment_status, v_start_time, v_doctor_id
    FROM doctor_available_time_segments d
    WHERE d.id = p_segment_id 
    FOR UPDATE;
    
    IF v_segment_status <> 0 THEN
        RAISE EXCEPTION 'Time segment already booked or unavailable (status must be 0)';
    END IF;

    -- 2. Insert appointment with doctor_id
    INSERT INTO doctor_appointment(
        doctor_id,
        time_segment_id, 
        patient_id, 
        appointment_time, 
        status
    )
    VALUES (
        v_doctor_id,
        p_segment_id, 
        p_patient_id, 
        v_start_time,
        1
    )
    RETURNING 
        doctor_appointment.appointment_id, 
        doctor_appointment.time_segment_id, 
        doctor_appointment.patient_id, 
        doctor_appointment.status
    INTO 
        v_appointment_id, 
        v_time_segment_id, 
        v_return_patient_id, 
        v_appointment_status;

    -- 3. Update time segment status to booked (1)
    UPDATE doctor_available_time_segments SET status = 1 WHERE id = p_segment_id;

    -- 4. Set the output parameters
    appointment_id := v_appointment_id;
    time_segment_id := v_time_segment_id;
    patient_id := v_return_patient_id;
    status := v_appointment_status;
    
    RETURN NEXT;
END;
$$;

-- Atomic cancel appointment function
CREATE OR REPLACE FUNCTION cancel_appointment_atomic(
    appt_id INT,
    by_doctor BOOL DEFAULT FALSE
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    seg_id INT;
    new_status SMALLINT;
BEGIN
    -- Check time_segment_id and lock the row
    SELECT time_segment_id INTO seg_id FROM doctor_appointment WHERE appointment_id=appt_id FOR UPDATE;
    IF seg_id IS NULL THEN
        RAISE EXCEPTION 'No such appointment';
    END IF;

    -- Update appointment status to cancelled (-1)
    UPDATE doctor_appointment SET status=-1 WHERE appointment_id=appt_id;

    -- Determine the next state of time segment according to by_doctor
    IF NOT by_doctor THEN
        new_status := 0; -- available
    ELSE
        new_status := -1; -- blocked (doctor-initiated cancellation)
    END IF;
    
    UPDATE doctor_available_time_segments SET status=new_status WHERE id=seg_id;

    RETURN 'OK';
END;
$$;


-- Atomic reactivate time segment function 
CREATE OR REPLACE FUNCTION reactivate_time_segment_atomic(
    segment_id INT
)
RETURNS TEXT
LANGUAGE plpgsql AS $$
DECLARE
    old_status SMALLINT;
BEGIN
    SELECT status INTO old_status FROM doctor_available_time_segments WHERE id=segment_id FOR UPDATE;
    IF old_status NOT IN (-1, 0) THEN  -- Only allow reactivation from blocked (-1) or available (0)
        RAISE EXCEPTION 'Time segment can only be reactivated from blocked (-1) or available (0) status';
    END IF;

    UPDATE doctor_available_time_segments SET status=0 WHERE id=segment_id;  -- Set to available (0)

    RETURN 'OK';
END;
$$;




-- ──────────────────────────────────────────────────────────────────────────
-- 11. audit_log trigger: log cancel/reorder operations

-- 11.1 Record doctor_appointment.status changes
DROP TRIGGER IF EXISTS audit_doctor_appointments ON doctor_appointment;
DROP FUNCTION IF EXISTS trg_audit_appointment();

CREATE OR REPLACE FUNCTION trg_audit_appointment()
RETURNS TRIGGER AS $$
DECLARE
  actor_id INTEGER;
  actor_role TEXT;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
    actor_id := NEW.patient_id;
    actor_role := 'patient';

    INSERT INTO audit_log(entity, entity_id, action, performed_by, role, details)
    VALUES (
      'doctor_appointment',
      NEW.appointment_id,
      CASE 
        WHEN NEW.status = -1 THEN 'cancelled'
        WHEN NEW.status = 0 THEN 'pending'
        WHEN NEW.status = 1 THEN 'confirmed'
        ELSE 'unknown'
      END,
      actor_id,
      actor_role,
      json_build_object(
        'old_status', OLD.status,
        'new_status', NEW.status,
        'status_description', CASE 
          WHEN NEW.status = -1 THEN 'cancelled' 
          WHEN NEW.status = 0 THEN 'pending' 
          WHEN NEW.status = 1 THEN 'confirmed' 
          ELSE 'unknown' 
        END
      )
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE TRIGGER audit_doctor_appointments
AFTER UPDATE ON doctor_appointment
FOR EACH ROW
EXECUTE FUNCTION trg_audit_appointment();


-- 11.2 Record doctor_appointment_requests status changes 
DROP TRIGGER IF EXISTS audit_appointment_requests ON doctor_appointment_requests;
DROP FUNCTION IF EXISTS trg_audit_appointment_request();

CREATE OR REPLACE FUNCTION trg_audit_appointment_request()
RETURNS TRIGGER AS $$
DECLARE
  actor_id INTEGER;
  actor_role TEXT;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.status IS DISTINCT FROM NEW.status THEN
    -- doctor_id is preferred, followed by patient_id (applicable for approval or patient-initiated)
    IF NEW.doctor_id IS NOT NULL THEN
      actor_id := NEW.doctor_id;
      actor_role := 'doctor';
    ELSIF NEW.patient_id IS NOT NULL THEN
      actor_id := NEW.patient_id;
      actor_role := 'patient';
    ELSE
      actor_id := -1;  
      actor_role := 'unknown';
    END IF;

    INSERT INTO audit_log(entity, entity_id, action, performed_by, role, details)
    VALUES (
      'appointment_request',
      NEW.id,
      CASE 
        WHEN NEW.status = -1 THEN 'cancelled'
        WHEN NEW.status = 0 THEN 'pending'
        WHEN NEW.status = 1 THEN 'approved'
        ELSE 'unknown'
      END,
      actor_id,
      actor_role,
      json_build_object(
        'old_status', OLD.status,
        'new_status', NEW.status,
        'status_description', CASE 
          WHEN NEW.status = -1 THEN 'cancelled' 
          WHEN NEW.status = 0 THEN 'pending' 
          WHEN NEW.status = 1 THEN 'approved' 
          ELSE 'unknown' 
        END
      )
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_appointment_requests
  AFTER UPDATE ON doctor_appointment_requests
  FOR EACH ROW
  EXECUTE FUNCTION trg_audit_appointment_request();






-- ──────────────────────────────────────────────────────────────────────────
-- 12. Indexes: Speed up common queries

-- Doctor available time segments by doctor + time
CREATE INDEX idx_available_segments_doctor_date
  ON doctor_available_time_segments(doctor_id, start_time);

-- Patient-doctor relationship
CREATE INDEX idx_pd_patient
  ON patient_doctor(patient_id);
CREATE INDEX idx_pd_doctor
  ON patient_doctor(doctor_id);

-- Doctor shift by doctor + time
CREATE INDEX idx_shifts_doctor_date
  ON doctor_shifts(doctor_id, start_time);

-- Audit log query by entity
CREATE INDEX idx_audit_entity
  ON audit_log(entity, entity_id);








