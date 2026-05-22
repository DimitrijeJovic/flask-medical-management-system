-- 1. DEPARTMENTS
CREATE TABLE departments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    naziv VARCHAR(100) NOT NULL,
    opis TEXT
);

-- 2. USERS
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ime VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    role ENUM('admin','doktor','sestra') NOT NULL,
    department_id INT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(id)
        ON DELETE SET NULL
);

-- 3. PATIENTS
CREATE TABLE patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ime VARCHAR(100) NOT NULL,
    prezime VARCHAR(100) NOT NULL,
    jmbg VARCHAR(20) UNIQUE NOT NULL,
    telefon VARCHAR(20)
);

-- 4. APPOINTMENTS
CREATE TABLE appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    datum DATETIME NOT NULL,
    status ENUM('zakazano','zavrseno','otkazano') DEFAULT 'zakazano',

    FOREIGN KEY (patient_id) REFERENCES patients(id)
        ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES users(id)
        ON DELETE CASCADE
);

-- 5. MEDICAL_RECORDS
CREATE TABLE medical_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    doctor_id INT NOT NULL,
    dijagnoza TEXT NOT NULL,
    terapija TEXT,
    datum DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (patient_id) REFERENCES patients(id)
        ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES users(id)
        ON DELETE CASCADE
);