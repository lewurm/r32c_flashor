#!/usr/bin/env python
import sys, time
from SerialPort_linux import SerialPort, SerialPortException

# baudrate used for initialization
INIT_BAUDRATE = 9600
# baudrate used for communication with the internal bootloader after init
BOOTLOADER_BAUDRATE = 9600
# constant for output
SPLIT = 30

# contains the last received checksum from a READ, WRITE or CHECKSUM command
lastchecksum = 0

flashKey = -1
flashKeyAddr = -1

class FlashSequence(object):
	def __init__(self, address, data):
		self.address = address
		self.data = data

class MCUStatus(object):
	NOKEY=0
	WRONGKEY=1
	CORRECTKEY=2
	key = 0

	def setKeyStatus(self, key):
		self.key = key

	def getKeyStatus(self):
		return self.key


def dec2hex(n):
	"""return the hexadecimal string representation of integer n"""
	return "%X" % n

def sendbyte(byte):
	"""
	send a byte to the TTY-device
	"""
	tty.write(chr(byte))

def sendword(word):
	"""
	send a word to the TTY-device
	"""
	sendbyte(word & 0xFF)
	sendbyte((word >> 8) & 0xFF)

def senddword(dword):
	"""
	send a dword to the TTY-device
	"""
	sendbyte(dword & 0xFF)
	sendbyte((dword >> 8) & 0xFF)
	sendbyte((dword >> 16) & 0xFF)
	sendbyte((dword >> 24) & 0xFF)

def recvbyte():
	"""
	receive a byte from the TTY-device
	"""
	return ord(tty.read())

def recvchecksum():
	"""
	receive checksum from the bootROM firmware
	"""
	global lastchecksum
	lastchecksum = recvbyte()
	lastchecksum |= (recvbyte() << 8)

def bootromread(address, size):
	"""
	send a READ-command to the bootROM-firmware
	"""
	# send READ command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x02)
	if (recvbyte() != 0x82):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)
	# get binary stream of data
	data = []
	for _ in range(0, size):
		data.append(recvbyte())
	# get checksum
	recvchecksum()
	return data

def bootromwrite(address, size, data):
	"""
	send a WRITE-command to the bootROM-firmware
	"""
	# send WRITE command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x03)
	if (recvbyte() != 0x83):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)
	# write binary stream of data
	for i in range(0, size):
		sendbyte(data[i])
	# get checksum
	recvchecksum()

def bootromcall(address):
	"""
	send a CALL-command to the bootROM-firmware
	"""
	# send CALL command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x04)
	if (recvbyte() != 0x84):
		raise Exception
	# tell desired address
	senddword(address)
	# wait for return parameter - not needed here!
	#return recvbyte()

# TODO: test this function!
def bootromchecksum():
	"""
	send a CHECKSUM-command to the bootROM-firmware
	"""
	# call CHECKSUM command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x05)
	if (recvbyte() != 0x84):
		raise Exception
	# get checksum
	recvchecksum()

def bootrombaudrate(baudrate):
	"""
	send a BAUDRAME-command to the bootROM-firmware
	"""
	# send BAUDRATE command
	sendbyte(0x01)
	if (recvbyte() != 0xF1):
		raise Exception
	sendbyte(0x06)
	if (recvbyte() != 0x86):
		raise Exception
	# send desired baudrate
	senddword(baudrate)

def pkernchiperase():
	"""
	send a CHIPERASE-command to the pkernel-firmware
	"""
	sendbyte(0x15)
	if (recvbyte() != 0x45):
		raise Exception
	# wait till completion...
	if (recvbyte() != 0x23):
		raise Exception

def pkernerase(address, size):
	"""
	send a ERASE-command to the pkernel-firmware
	"""
	sendbyte(0x12)
	if (recvbyte() != 0x11):
		raise Exception
	senddword(address)
	sendword(size)
	if (recvbyte() != 0x18):
		raise Exception

def pkernwrite(address, size, data):
	"""
	send a WRITE-command to the pkernel-firmware
	"""
	# send WRITE command
	sendbyte(0x13)
	if (recvbyte() != 0x37):
		raise Exception
	# tell desired address and size
	senddword(address)
	sendword(size)

	# write binary stream of data
	for i in range(0, size):
		sendbyte(data[i])

	if (recvbyte() != 0x28):
		raise Exception

def readmhxfile(filename): # desired mhx filename
	"""
	proceeds a MHX-File
	"""
	filep = open(filename, "r")
	retval = [] # returns a list of FlashSequence objects
	linecount = 0
	for line in filep:
		linecount += 1
		# get rid of newline characters
		line = line.strip()
		# we're only interested in S2 (data sequence with 3 address bytes)
		# records by now
		if line[0:2] == "S3":
			byte_count = int(line[2:4], 16)
			# just to get sure, check if byte count field is valid
			if (len(line)-4) != (byte_count*2):
				print sys.argv[0] + ": Warning - inavlid byte count field in " + \
					sys.argv[1] + ":" + str(linecount) + ", skipping line!"
				continue

			# address and checksum bytes are not needed
			byte_count -= 5
			address = int(line[4:12], 16)
			print line[4:12] + "< hex  dec > " +str(address)
			datastr = line[12:12+byte_count*2]
			# convert data hex-byte-string to real byte data list
			data = []
			for i in range(0, len(datastr)/2):
				data.append(int(datastr[2*i:2*i+2], 16))

			# add flash sequence to our list
			retval.append(FlashSequence(address, data))
	filep.close()
	return retval

def clearStatus():
	sendbyte(0x50);

def getStatusKey(sendKey):
	sendbyte(0x70) # get status
	status1 = recvbyte()
	status2 = recvbyte()
	print "status1: " + dec2hex(status1)
	print "status2: " + dec2hex(status2)
	print "bootloader ready: " + str(testBit(status1, 7))
	print "erase fail: " + str(testBit(status1, 5))
	print "programming fail: " + str(testBit(status1, 4))
	key1 = testBit(status2, 2)
	key2 = testBit(status2, 3)

	status = MCUStatus()

	if key1 == 1 and key2 == 1:
		status.setKeyStatus(MCUStatus.CORRECTKEY)
		print "correct key"
	elif key1 == 1 and key2 == 0:
		status.setKeyStatus(MCUStatus.WRONGKEY)
		print "wrong key"
	elif key1 == 0 and key2 == 0:
		status.setKeyStatus(MCUStatus.NOKEY)
		print "no key",
		if sendKey == 1:
			sendFlashKey()
			print " - sending key"
		else:
			print
	else:
		print "w00t"
		raise Exception('wrongkeybits!')

	return status

def getStatus():
	return getStatusKey(0)

def testBit(byte, pos):
	bitmask = 1 << pos
	return (byte & bitmask) >> pos

def sendKeyAddr(addr):
	sendbyte(0x48)
	sendbyte((addr >> 24) & 0xFF)
	sendbyte(0xF5)
	sendbyte(addr& 0xFF)
	sendbyte((addr >> 8) & 0xFF)
	sendbyte((addr >> 16) & 0xFF)

def sendPageAddr(addr, cmd):
	sendbyte(0x48)
	sendbyte((addr >> 24) & 0xFF)
	sendbyte(cmd)
	sendbyte((addr >> 8) & 0xFF)
	sendbyte((addr >> 16) & 0xFF)


def sendKey(addr, key):
	print "Sending key: " + dec2hex(key) + " for addr: " + dec2hex(addr)
	sendKeyAddr(addr)
	sendbyte(0x07)
	for i in range(7):
		sendbyte((key >> i) & 0xFF)

def readPage(addr):
	sendPageAddr(addr, 0xff)
	for i in range(0, 255):
		#print "byte" + str(i) + ": " + dec2hex(recvbyte())
		print dec2hex(recvbyte()),

def writePage(addr, data):
	clearStatus()
	getStatus()
	sendPageAddr(addr, 0x41)
	for byte in data:
		sendbyte(byte)
	print "Data written"
	time.sleep(0.5) #wait 500ms
	getStatus()

def writeProg(prgseqs):
	lastPos = 255	
	lastAddr = -256
	pageAddr = 0
	page = []

	for i in range(0,len(prgseqs)):
		addr = prgseqs[i].address
		mod = addr%256
		if mod < lastPos or (addr-lastAddr) >= 256:
			#print "new page! old has " + str(len(page)) + " bytes"
			if len(page) < 256:
				for j in range(len(page), 256):
					page.append(0)
			newpage = []
			if len(page) > 255:
				for j in range(256, len(page)):
					newpage.append(page[256])
					del page[256]
			if lastAddr >= 0:
				#print page
				#for byte in page:
					#print dec2hex(byte),
				print "Programming to addr " + dec2hex(pageAddr)
				writePage(pageAddr, page)

			page = newpage
			pageAddr = addr - mod

		if len(page) != mod:
			#print "need filling"
			for j in range(0,len(page)-mod):
				page.append(0)
		lastPos = mod 
		lastAddr = addr

		data = prgseqs[i].data

		for j in range(0,len(data)):
			page.append(data[j])

		#print prgseqs[i].data
		#print str(mod) + "< mod size > " + str(len(data))

def sendFlashKey():
	correct = 0
	global flashKey
	global flashKeyAddr
	if getStatus().getKeyStatus() == MCUStatus.CORRECTKEY:
		correct = 1
	else:
		if flashKey != -1:
			sendKey(flashKeyAddr, flashKey)
			status = getStatus()
			if status.getKeyStatus() != MCUStatus.CORRECTKEY:
				print "w00t, key changed?!?"
			clearStatus()

		else:
			for i in range(0xFFFFFFE8, 0xFFFFFFEE):

				sendKey(i, 0x00000000000000)
				status = getStatus()
				if status.getKeyStatus() == MCUStatus.CORRECTKEY:
					flashKey = 0x00000000000000
					flashKeyAddr = i
					correct = 1
					break
				clearStatus()


				sendKey(i, 0xFFFFFFFFFFFFFF)
				status = getStatus()
				if status.getKeyStatus() == MCUStatus.CORRECTKEY:
					flashKey = 0xFFFFFFFFFFFFFF
					flashKeyAddr = i
					correct = 1
					break
				clearStatus()

	return correct



def usage(execf):
	"""
	print usage of frprog
	"""
	print "Usage: " + execf + " <target mhx-file> [-d DEVICE]"

def main(argv=None):
	"""
	main function of frprog
	"""
	# check command line arguments
	if argv is None:
		argv = sys.argv

	if len(argv) == 2 and (argv[1] == "-v" or argv[1] == "--version"):
		print "Version: %VERSION%"
		return 0

	#TODO: ...
	#if len(argv) != 2 and len(argv) != 4:
	if len(argv) != 2:
		usage(argv[0])
		return 1

	# standard serial device to communicate with
	device = "/dev/ttyUSB0"

	# overrule standard device if provided with -d
	if len(argv) == 4:
		if argv[2] == "-d":
			device = argv[3]
		else:
			usage(argv[0])
			return 1

	# read in data from mhx-files before starting
	try:
		prgseqs = readmhxfile(argv[1])
	except IOError as error:
		print argv[0] + ": Error - couldn't open file " + error.filename + "!"
		return 1

	print "Initializing serial port..."
	global tty
	try:
		tty = SerialPort(device, 100, INIT_BAUDRATE)
	except SerialPortException as error:
		print error + " Device: " + device + "!"
		return 1

	
	raw_input("Please push the RESET button on your board and press any ENTER to continue...")
	#TODO: wait for user input

	for i in range(16):
		sendbyte(0x00)
		time.sleep(0.021) #wait 21ms
	
	sendbyte(0xb0) # set 9600 baud
	print "status byte after baudset: ", recvbyte()

	sendbyte(0xfb) # get version

	version = ""
	for i in range(8):
		version = version + chr(recvbyte())

	print "chipversion: ", version

	clearStatus()

	if sendFlashKey() == 0:
		print "No Valid Key found! Powercycle the board or provide correct key!"
		return 1

	#readPage(0xffff0000)
	clearStatus()
	writeProg(prgseqs)
	time.sleep(0.5) #wait 500ms
	getStatus()
	readPage(0xffff0000)
	

	# save time at this point for evaluating the duration at the end
	starttime = time.time()


if __name__ == '__main__':
	sys.exit(main())
